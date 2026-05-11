"""
Motor de Regras SAFX — avalia condições e aplica ações sobre tabelas carregadas.

Suporta:
  • Condições por campo (único ou múltiplos) com lógica AND/OR
  • Ações: valor constante, fórmula matemática, copiar campo,
           formatação, mapeamento lookup, busca em API externa
  • Pacotes de regras (workflows encadeados)
  • Persistência em ~/.safx_editor/rules.json
"""
from __future__ import annotations

import json
import logging
import math
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

RULES_FILE = Path.home() / ".safx_editor" / "rules.json"

# ─── Catálogos de opções ──────────────────────────────────────────────────────

CONDITION_OPS: Dict[str, str] = {
    "equals":        "igual a",
    "not_equals":    "diferente de",
    "contains":      "contém",
    "not_contains":  "não contém",
    "starts_with":   "começa com",
    "ends_with":     "termina com",
    "greater_than":  "maior que (número)",
    "less_than":     "menor que (número)",
    "greater_equal": "≥ maior ou igual",
    "less_equal":    "≤ menor ou igual",
    "is_empty":      "está vazio",
    "is_not_empty":  "não está vazio",
    "regex":         "expressão regular",
    "in_list":       "valor está na lista (a,b,c)",
    "not_in_list":   "valor não está na lista",
}

ACTION_TYPES: Dict[str, str] = {
    "set_value":    "Definir valor constante",
    "set_formula":  "Fórmula matemática  (ex: {PRECO}*{QTDE})",
    "copy_field":   "Copiar de outro campo",
    "format":       "Formatar campo",
    "lookup":       "Substituir por mapeamento  (chave=valor; ...)",
    "table_lookup": "Buscar de outra tabela  (join/filtro)",
    "api_fetch":    "Buscar de API externa",
    "concat":       "Concatenar campos  (ex: {NOME}+' '+{SOBRENOME})",
    "conditional":  "Valor condicional  (se → então → senão)",
}

FORMAT_TYPES: Dict[str, str] = {
    "uppercase":   "MAIÚSCULAS",
    "lowercase":   "minúsculas",
    "titlecase":   "Primeira Letra Maiúscula",
    "strip":       "Remover espaços extras",
    "cpf":         "Máscara CPF  (000.000.000-00)",
    "cnpj":        "Máscara CNPJ  (00.000.000/0000-00)",
    "date_br":     "Data BR  (DD/MM/AAAA)",
    "date_iso":    "Data ISO  (AAAA-MM-DD)",
    "zero_pad":    "Preencher zeros à esquerda  (arg = largura)",
    "number_br":   "Número BR  (1.234,56)",
    "number_us":   "Número US  (1,234.56)",
    "remove_chars":"Remover caracteres  (arg = chars a remover)",
    "replace":     "Substituir texto  (arg = antigo|novo)",
    "extract_re":  "Extrair com regex  (arg = padrão)",
    "round_num":   "Arredondar número  (arg = casas decimais)",
}

# Contexto seguro para eval de fórmulas
_SAFE_BUILTINS: Dict[str, Any] = {
    "abs": abs, "round": round, "min": min, "max": max,
    "int": int, "float": float, "str": str, "len": len,
    "sum": sum, "bool": bool,
    "sqrt": math.sqrt, "pow": math.pow,
    "log": math.log, "log10": math.log10,
    "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e,
    "True": True, "False": False, "None": None,
}


# ─── Avaliação de fórmulas ────────────────────────────────────────────────────

def _resolve_row_ctx(row: Dict[str, Any]) -> Dict[str, Any]:
    """Cria contexto de variáveis a partir dos campos da linha."""
    ctx = dict(_SAFE_BUILTINS)
    for k, v in row.items():
        safe_k = re.sub(r'\W', '_', str(k))
        try:
            ctx[safe_k] = float(str(v).replace(',', '.'))
        except (TypeError, ValueError):
            ctx[safe_k] = str(v) if v is not None else ""
    return ctx


def _expand_refs(expr: str, row: Dict[str, Any]) -> str:
    """Substitui {CAMPO} pelo valor numérico ou string citada do campo."""
    def _repl(m: re.Match) -> str:
        field = m.group(1)
        val = row.get(field)
        if val is None:
            return '""'
        try:
            return str(float(str(val).replace(',', '.')))
        except (TypeError, ValueError):
            escaped = str(val).replace('"', '\\"')
            return f'"{escaped}"'
    return re.sub(r'\{([^}]+)\}', _repl, expr)


def eval_formula(formula: str, row: Dict[str, Any]) -> Optional[Any]:
    """Avalia fórmula Python-like com referências a campos {CAMPO}."""
    expr = _expand_refs(formula, row)
    ctx = _resolve_row_ctx(row)
    try:
        return eval(expr, {"__builtins__": {}}, ctx)  # noqa: S307
    except Exception as exc:
        logger.debug(f"Fórmula '{formula}' → '{expr}' erro: {exc}")
        return None


# ─── Formatação de campos ─────────────────────────────────────────────────────

def apply_format(value: Any, fmt: str, fmt_arg: str = "") -> str:
    """Aplica uma das formatações disponíveis ao valor."""
    s = str(value) if value is not None else ""

    if fmt == "uppercase":
        return s.upper()
    if fmt == "lowercase":
        return s.lower()
    if fmt == "titlecase":
        return s.title()
    if fmt == "strip":
        return " ".join(s.split())
    if fmt == "cpf":
        d = re.sub(r'\D', '', s)
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else s
    if fmt == "cnpj":
        d = re.sub(r'\D', '', s)
        return (f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
                if len(d) == 14 else s)
    if fmt == "date_br":
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s
    if fmt == "date_iso":
        m = re.match(r'(\d{2})/(\d{2})/(\d{4})', s)
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else s
    if fmt == "zero_pad":
        try:
            return s.zfill(int(fmt_arg))
        except (ValueError, TypeError):
            return s
    if fmt == "number_br":
        try:
            n = float(s.replace(',', '.'))
            return f"{n:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        except (ValueError, TypeError):
            return s
    if fmt == "number_us":
        try:
            return f"{float(s.replace(',', '.')):.2f}"
        except (ValueError, TypeError):
            return s
    if fmt == "remove_chars":
        for ch in fmt_arg:
            s = s.replace(ch, "")
        return s
    if fmt == "replace":
        parts = fmt_arg.split("|", 1)
        if len(parts) == 2:
            return s.replace(parts[0], parts[1])
        return s
    if fmt == "extract_re":
        try:
            m = re.search(fmt_arg, s)
            return m.group(0) if m else s
        except re.error:
            return s
    if fmt == "round_num":
        try:
            places = int(fmt_arg) if fmt_arg else 2
            return str(round(float(s.replace(',', '.')), places))
        except (ValueError, TypeError):
            return s
    return s


# ─── Avaliação de condições ───────────────────────────────────────────────────

def check_condition(cond: Dict, row: Dict[str, Any]) -> bool:
    """Avalia uma condição individual contra uma linha de dados."""
    field = cond.get("field", "")
    op = cond.get("op", "equals")
    ref_value = str(cond.get("value", ""))
    cell = str(row.get(field, "")) if row.get(field) is not None else ""

    if op == "equals":
        return cell.strip().lower() == ref_value.strip().lower()
    if op == "not_equals":
        return cell.strip().lower() != ref_value.strip().lower()
    if op == "contains":
        return ref_value.lower() in cell.lower()
    if op == "not_contains":
        return ref_value.lower() not in cell.lower()
    if op == "starts_with":
        return cell.lower().startswith(ref_value.lower())
    if op == "ends_with":
        return cell.lower().endswith(ref_value.lower())
    if op == "is_empty":
        return cell.strip() == ""
    if op == "is_not_empty":
        return cell.strip() != ""
    if op == "regex":
        try:
            return bool(re.search(ref_value, cell))
        except re.error:
            return False
    if op == "in_list":
        items = [x.strip() for x in ref_value.split(",")]
        return cell.strip() in items
    if op == "not_in_list":
        items = [x.strip() for x in ref_value.split(",")]
        return cell.strip() not in items

    # Comparações numéricas
    try:
        cn = float(cell.replace(',', '.'))
        vn = float(ref_value.replace(',', '.'))
        if op == "greater_than":
            return cn > vn
        if op == "less_than":
            return cn < vn
        if op == "greater_equal":
            return cn >= vn
        if op == "less_equal":
            return cn <= vn
    except (ValueError, TypeError):
        if op == "greater_than":
            return cell > ref_value
        if op == "less_than":
            return cell < ref_value
        if op == "greater_equal":
            return cell >= ref_value
        if op == "less_equal":
            return cell <= ref_value

    return False


def evaluate_conditions(conditions: List[Dict], logic: str, row: Dict) -> bool:
    """Avalia lista de condições com lógica AND/OR."""
    if not conditions:
        return True  # Sem condições → aplica a todos os registros
    results = [check_condition(c, row) for c in conditions]
    return any(results) if logic == "OR" else all(results)


# ─── Motor principal ──────────────────────────────────────────────────────────

class RuleEngine:
    """Motor de regras SAFX: carrega, salva e executa regras sobre tabelas."""

    def __init__(self):
        self._rules: List[Dict] = []
        self._packages: List[Dict] = []
        self._load()

    # ── Persistência ──────────────────────────────────────────────────────────

    def _load(self):
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        if RULES_FILE.exists():
            try:
                data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
                self._rules = data.get("rules", [])
                self._packages = data.get("packages", [])
            except Exception as exc:
                logger.warning(f"Erro ao carregar regras: {exc}")

    def save(self):
        try:
            payload = {"rules": self._rules, "packages": self._packages}
            RULES_FILE.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as exc:
            logger.error(f"Erro ao salvar regras: {exc}")

    # ── CRUD de regras ────────────────────────────────────────────────────────

    @property
    def rules(self) -> List[Dict]:
        return list(self._rules)

    @property
    def packages(self) -> List[Dict]:
        return list(self._packages)

    def get_rule(self, rule_id: str) -> Optional[Dict]:
        return next((r for r in self._rules if r.get("id") == rule_id), None)

    def get_package(self, pkg_id: str) -> Optional[Dict]:
        return next((p for p in self._packages if p.get("id") == pkg_id), None)

    def upsert_rule(self, rule: Dict) -> str:
        if not rule.get("id"):
            rule["id"] = str(uuid.uuid4())
        for i, r in enumerate(self._rules):
            if r.get("id") == rule["id"]:
                self._rules[i] = rule
                self.save()
                return rule["id"]
        self._rules.append(rule)
        self.save()
        return rule["id"]

    def delete_rule(self, rule_id: str):
        self._rules = [r for r in self._rules if r.get("id") != rule_id]
        for pkg in self._packages:
            pkg["rule_ids"] = [rid for rid in pkg.get("rule_ids", [])
                               if rid != rule_id]
        self.save()

    def upsert_package(self, pkg: Dict) -> str:
        if not pkg.get("id"):
            pkg["id"] = str(uuid.uuid4())
        pkg.setdefault("rule_ids", [])
        for i, p in enumerate(self._packages):
            if p.get("id") == pkg["id"]:
                self._packages[i] = pkg
                self.save()
                return pkg["id"]
        self._packages.append(pkg)
        self.save()
        return pkg["id"]

    def delete_package(self, pkg_id: str):
        self._packages = [p for p in self._packages if p.get("id") != pkg_id]
        self.save()

    # ── Execução ──────────────────────────────────────────────────────────────

    def execute_rule(self, rule: Dict, db, table_name: str,
                     row_ids: Optional[List[int]] = None
                     ) -> Tuple[int, List[str]]:
        """Executa a regra sobre todos os registros (ou apenas row_ids).
        Retorna (linhas_modificadas, erros).
        """
        from core.database import ROW_ID_COL

        conditions = rule.get("conditions", [])
        logic = rule.get("condition_logic", "AND")
        actions = rule.get("actions", [])
        modified = 0
        errors: List[str] = []

        # Carrega dados da tabela
        try:
            with db._lock:
                cur = db.conn.cursor()
                if row_ids:
                    placeholders = ",".join("?" for _ in row_ids)
                    cur.execute(
                        f'SELECT * FROM "{table_name}" '
                        f'WHERE "{ROW_ID_COL}" IN ({placeholders})',
                        row_ids)
                else:
                    cur.execute(f'SELECT * FROM "{table_name}"')
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
        except Exception as exc:
            return 0, [f"Erro ao ler tabela: {exc}"]

        for row_tuple in rows:
            row = dict(zip(cols, row_tuple))
            row_id = row.get(ROW_ID_COL)
            if row_id is None:
                continue

            if not evaluate_conditions(conditions, logic, row):
                continue

            updates: Dict[str, Any] = {}
            for action in actions:
                atype = action.get("type", "set_value")
                field = action.get("field", "")
                if not field or field not in cols:
                    continue
                try:
                    new_val = self._apply_action(atype, action, field, row, errors, db)
                    if new_val is not None:
                        updates[field] = new_val
                        row[field] = new_val  # cascata dentro da mesma regra
                except Exception as exc:
                    errors.append(f"Ação [{atype}] campo '{field}': {exc}")

            if updates:
                set_clause = ", ".join(f'"{k}" = ?' for k in updates)
                vals = list(updates.values()) + [row_id]
                try:
                    with db._lock:
                        db.conn.execute(
                            f'UPDATE "{table_name}" SET {set_clause} '
                            f'WHERE "{ROW_ID_COL}" = ?',
                            vals)
                        db.conn.execute("COMMIT")
                    modified += 1
                except Exception as exc:
                    errors.append(f"Erro ao salvar linha {row_id}: {exc}")

        return modified, errors

    def _apply_action(self, atype: str, action: Dict,
                      field: str, row: Dict, errors: List[str],
                      db=None) -> Optional[str]:
        """Aplica uma ação individual e retorna o novo valor (string) ou None."""

        if atype == "set_value":
            return str(action.get("value", ""))

        if atype in ("set_formula", "concat"):
            formula = action.get("formula", "0")
            result = eval_formula(formula, row)
            if result is None:
                return None
            # Arredonda floats limpos
            if isinstance(result, float) and result == int(result):
                return str(int(result))
            return str(result)

        if atype == "copy_field":
            src = action.get("source_field", "")
            return str(row.get(src, "")) if src in row else None

        if atype == "format":
            fmt = action.get("format_type", "uppercase")
            arg = action.get("format_arg", "")
            return apply_format(row.get(field, ""), fmt, arg)

        if atype == "lookup":
            raw = action.get("mapping_raw", "")
            mapping = {}
            for pair in raw.split(";"):
                kv = pair.strip().split("=", 1)
                if len(kv) == 2:
                    mapping[kv[0].strip()] = kv[1].strip()
            cell = str(row.get(field, ""))
            return mapping.get(cell, None)  # None = não altera se não mapeado

        if atype == "conditional":
            formula = action.get("formula", "")
            then_val = str(action.get("then_value", ""))
            else_val = str(action.get("else_value", ""))
            result = eval_formula(formula, row)
            return then_val if result else else_val

        if atype == "table_lookup":
            return self._table_lookup_action(action, row, db, errors)

        if atype == "api_fetch":
            return self._api_action(action, row, errors)

        return None

    def _table_lookup_action(self, action: Dict, row: Dict,
                             db, errors: List[str]) -> Optional[str]:
        """Busca um valor em outra tabela usando um campo da linha atual como chave."""
        if db is None:
            errors.append("table_lookup: banco de dados não disponível")
            return None
        src_table = action.get("src_table", "")
        src_match = action.get("src_match_field", "")
        local_match = action.get("local_match_field", "")
        return_field = action.get("return_field", "")
        default_val = str(action.get("default_value", ""))
        match_op = action.get("match_op", "equals")

        if not src_table or not return_field:
            return None

        local_val = str(row.get(local_match, "")) if local_match else ""

        try:
            with db._lock:
                cur = db.conn.cursor()
                if src_match and local_val:
                    if match_op == "equals":
                        cur.execute(
                            f'SELECT "{return_field}" FROM "{src_table}" '
                            f'WHERE "{src_match}" = ? LIMIT 1',
                            [local_val])
                    elif match_op == "contains":
                        cur.execute(
                            f'SELECT "{return_field}" FROM "{src_table}" '
                            f'WHERE "{src_match}" LIKE ? LIMIT 1',
                            [f"%{local_val}%"])
                    elif match_op == "starts_with":
                        cur.execute(
                            f'SELECT "{return_field}" FROM "{src_table}" '
                            f'WHERE "{src_match}" LIKE ? LIMIT 1',
                            [f"{local_val}%"])
                    else:
                        cur.execute(
                            f'SELECT "{return_field}" FROM "{src_table}" '
                            f'WHERE "{src_match}" = ? LIMIT 1',
                            [local_val])
                else:
                    cur.execute(
                        f'SELECT "{return_field}" FROM "{src_table}" LIMIT 1')
                result = cur.fetchone()
            if result and result[0] is not None:
                return str(result[0])
            return default_val
        except Exception as exc:
            errors.append(f"table_lookup '{src_table}': {exc}")
            return default_val

    def _api_action(self, action: Dict, row: Dict, errors: List[str]) -> Optional[str]:
        try:
            import requests  # noqa: PLC0415
        except ImportError:
            errors.append("requests não instalado — pip install requests")
            return None
        url_tpl = action.get("url", "")
        url = re.sub(r'\{([^}]+)\}', lambda m: str(row.get(m.group(1), "")), url_tpl)
        headers = action.get("headers", {})
        resp_path = action.get("response_field", "")
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            if resp_path:
                val: Any = data
                for key in resp_path.split("."):
                    val = val.get(key, "") if isinstance(val, dict) else ""
                return str(val)
            return str(data)
        except Exception as exc:
            errors.append(f"API '{url}': {exc}")
            return None

    # ── Execução de pacote ────────────────────────────────────────────────────

    def execute_package(self, pkg_id: str, db, table_name: str,
                        row_ids: Optional[List[int]] = None
                        ) -> List[Tuple[str, int, List[str]]]:
        """Executa todas as regras habilitadas de um pacote em sequência."""
        pkg = self.get_package(pkg_id)
        if not pkg:
            return []
        results: List[Tuple[str, int, List[str]]] = []
        for rule_id in pkg.get("rule_ids", []):
            rule = self.get_rule(rule_id)
            if not rule or not rule.get("enabled", True):
                continue
            n, errs = self.execute_rule(rule, db, table_name, row_ids)
            results.append((rule.get("name", rule_id), n, errs))
            if pkg.get("stop_on_error", False) and errs:
                break
        return results
