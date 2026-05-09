"""
Banco de dados SQLite in-memory para armazenamento temporário de SAFX.
Os dados NÃO são persistidos - servem apenas para manipulação e ajustes.
"""
import sqlite3
import logging
import threading
import datetime as _dt
from typing import List, Dict, Tuple, Optional, Any, Set, cast

from .layout_manager import TableLayout

logger = logging.getLogger(__name__)

# Coluna interna de controle de linha
ROW_ID_COL = '_row_id'


def strip_leading_sql_line_comments(sql: str) -> str:
    """
    Remove linhas vazias e comentários ``--`` do início do script.
    O SQLite aceita comentários antes do SELECT; esta função alinha a
    deteção SELECT/DML e EXPLAIN com o que o motor realmente executa.
    """
    if not sql:
        return ''
    lines = sql.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.startswith('--'):
            i += 1
            continue
        break
    return '\n'.join(lines[i:]).strip()


def sql_cell_text_for_import(v: Any) -> str:
    """Normaliza valor de célula (planilha) para TEXT no SQLite (espaços, etc.)."""
    if v is None:
        return ''
    return str(v).strip()


def format_sqlite_error(exc: sqlite3.Error) -> str:
    """
    Mensagem detalhada para diagnóstico (subtipo/código SQLite quando disponíveis).
    """
    name = getattr(exc, 'sqlite_errorname', None) or ''
    code = getattr(exc, 'sqlite_errorcode', None)
    lines = [
        '[Erro de execução SQL — confira nomes de tabelas/colunas e o ON do JOIN]',
    ]
    if name:
        lines.append(f'Subtipo SQLite: {name}')
    if code is not None:
        lines.append(f'Código numérico: {code}')
    lines.append(f'Mensagem: {exc}')
    return '\n'.join(lines)


class SAFXDatabase:
    """Banco SQLite in-memory para tabelas SAFX."""

    def __init__(self):
        # isolation_level=None = autocommit total, controle 100% manual
        self.conn = sqlite3.connect(':memory:', check_same_thread=False,
                                    isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.loaded_tables: Dict[str, TableLayout] = {}
        self._in_manual_transaction = False  # rastreia transações manuais
        self._change_log: List[Dict] = []    # log de todas as alterações commitadas
        # Lotes desfazíveis: cada lote = lista de {table, row_id, field, old_value, new_value}
        self._undo_batches: List[List[Dict[str, Any]]] = []
        self._external_tables: set = set()   # tabelas externas (Excel/CSV importados)
        self._external_schemas: Dict[str, Tuple[str, ...]] = {}
        # ^ layout temporário: colunas por nome físico (atualizado a cada import externa)

        # Otimizações para arquivos grandes
        self.conn.execute("PRAGMA journal_mode = MEMORY")
        self.conn.execute("PRAGMA synchronous = OFF")
        self.conn.execute("PRAGMA temp_store = MEMORY")
        self.conn.execute("PRAGMA cache_size = -65536")   # 64MB cache
        self.conn.execute("PRAGMA mmap_size = 536870912") # 512MB mmap

    @property
    def in_transaction(self) -> bool:
        """Retorna True se uma transação manual estiver ativa."""
        return self._in_manual_transaction

    def begin(self) -> Tuple[bool, str]:
        """Inicia transação manual (BEGIN)."""
        with self._lock:
            try:
                self.conn.execute("BEGIN")
                self._in_manual_transaction = True
                return True, "Transacao iniciada (BEGIN)"
            except sqlite3.Error as e:
                return False, f"Erro ao iniciar transacao: {e}"

    def commit(self) -> Tuple[bool, str]:
        """Confirma transação manual (COMMIT)."""
        with self._lock:
            try:
                self.conn.execute("COMMIT")
                self._in_manual_transaction = False
                return True, "COMMIT realizado com sucesso"
            except sqlite3.Error as e:
                self._in_manual_transaction = False
                return False, f"Erro no COMMIT: {e}"

    def rollback(self) -> Tuple[bool, str]:
        """Desfaz transação manual (ROLLBACK)."""
        with self._lock:
            try:
                self.conn.execute("ROLLBACK")
                self._in_manual_transaction = False
                return True, "ROLLBACK realizado - alteracoes desfeitas"
            except sqlite3.Error as e:
                self._in_manual_transaction = False
                return False, f"Erro no ROLLBACK: {e}"

    # ─── Log de Alterações ────────────────────────────────────────────────────

    def add_to_change_log(self, table: str, row_id, field: str,
                          old_value: str, new_value: str,
                          source: str = 'manual'):
        """Registra uma alteração commitada no log."""
        self._change_log.append({
            'timestamp': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'table': table,
            'row_id': row_id,
            'field': field,
            'old_value': old_value,
            'new_value': new_value,
            'source': source,
        })

    def add_sql_to_change_log(self, sql_stmt: str, affected: int):
        """Registra um UPDATE/INSERT/DELETE SQL no log."""
        self._change_log.append({
            'timestamp': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'table': '(SQL)',
            'row_id': '-',
            'field': f'{affected} linha(s)',
            'old_value': '',
            'new_value': sql_stmt[:200],
            'source': 'sql',
        })

    def get_change_log(self) -> List[Dict]:
        """Retorna cópia do log de alterações."""
        return list(self._change_log)

    def clear_change_log(self):
        """Limpa o log de alterações."""
        self._change_log.clear()

    def record_undo_batch(self, entries: List[Dict[str, Any]]) -> None:
        """
        Registra um lote desfazível (último «Confirmar» na grade Dados,
        edição na grade SQL, ou colar em massa).
        Cada entrada: table, row_id, field, old_value, new_value.
        """
        if not entries:
            return
        batch = []
        for e in entries:
            batch.append({
                'table': str(e.get('table', '')),
                'row_id': int(e['row_id']),
                'field': str(e.get('field', '')),
                'old_value': str(e.get('old_value', '')),
                'new_value': str(e.get('new_value', '')),
            })
        self._undo_batches.append(batch)

    def can_undo(self) -> bool:
        return bool(self._undo_batches)

    def undo_last_batch(self) -> Tuple[bool, str]:
        """Restaura valores anteriores do último lote confirmado/editado."""
        if not self._undo_batches:
            return False, 'Nada para desfazer.'
        batch = self._undo_batches.pop()
        restored = 0
        errors = 0
        for e in batch:
            try:
                ok = self.update_cell(
                    e['table'], cast(int, e['row_id']),
                    e['field'], e['old_value'])
                if ok:
                    restored += 1
                else:
                    errors += 1
            except Exception as ex:
                errors += 1
                logger.warning(f'Undo célula falhou: {ex}')
        self._change_log.append({
            'timestamp': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'table': '(app)',
            'row_id': '-',
            'field': 'DESFAZER',
            'old_value': '',
            'new_value': (
                f'Revertido lote de {len(batch)} edição(ões) '
                f'({restored} célula(s) restauradas no SQLite)'
                + (f'; {errors} falha(s)' if errors else '')),
            'source': 'undo',
        })
        return True, (
            f'{restored} célula(s) restaurada(s) ao estado anterior.'
            + (f' ({errors} falha(s))' if errors else ''))

    # ─── Tabelas externas (Excel / CSV para JOIN) ────────────────────────────

    def import_external_table(self, table_name: str,
                              columns: List[str],
                              rows: List[List],
                              progress_cb=None) -> Tuple[int, str]:
        """
        Cria (ou substitui) uma tabela temporária no SQLite com dados externos
        (Excel, CSV...). Retorna (número de linhas importadas, nome físico da tabela).
        """
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
        raw_safe = [''.join(c if c.isalnum() or c == '_' else '_' for c in str(col))
                    for col in columns]
        # CREATE TABLE falha se houver nomes duplicados após sanitização
        safe_cols: List[str] = []
        seen: Dict[str, int] = {}
        for c in raw_safe:
            base = c or 'COL'
            n = seen.get(base, 0)
            seen[base] = n + 1
            safe_cols.append(base if n == 0 else f'{base}_{n + 1}')

        insert_cols = ', '.join(f'"{c}"' for c in safe_cols)
        placeholders = ','.join('?' * len(safe_cols))
        insert_sql = (
            f'INSERT INTO "{safe}" ({insert_cols}) VALUES ({placeholders})'
        )

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(f'DROP TABLE IF EXISTS "{safe}"')
            col_parts = [f'"{ROW_ID_COL}" INTEGER PRIMARY KEY AUTOINCREMENT']
            col_parts += [f'"{c}" TEXT' for c in safe_cols]
            cols_def = ', '.join(col_parts)
            cur.execute(f'CREATE TABLE "{safe}" ({cols_def})')

            batch_size = 5_000
            total = 0
            buf = []

            for row in rows:
                padded = list(row) + [''] * max(0, len(safe_cols) - len(row))
                buf.append([sql_cell_text_for_import(v) for v in padded[:len(safe_cols)]])
                total += 1
                if len(buf) >= batch_size:
                    cur.executemany(insert_sql, buf)
                    buf.clear()
                    if progress_cb:
                        progress_cb(total)

            if buf:
                cur.executemany(insert_sql, buf)
            self.conn.commit()
            self._external_tables.add(safe)
            self._external_schemas[safe] = tuple(safe_cols)

        return total, safe

    def drop_external_table(self, table_name: str):
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
        with self._lock:
            self.conn.execute(f'DROP TABLE IF EXISTS "{safe}"')
            self.conn.commit()
        self._external_tables.discard(safe)
        self._external_schemas.pop(safe, None)

    def list_external_tables(self) -> List[str]:
        return list(self._external_tables)

    def load_table(self, table_name: str, layout: TableLayout,
                   data: List[Dict],
                   progress_callback=None) -> int:
        """
        Carrega dados de uma tabela SAFX no SQLite.
        Retorna número de linhas carregadas.
        """
        with self._lock:
            self.loaded_tables[table_name] = layout

            cur = self.conn.cursor()
            cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')

            # Cria tabela com _row_id + todos os campos como TEXT
            col_defs = [f'"{ROW_ID_COL}" INTEGER PRIMARY KEY AUTOINCREMENT']
            for f in layout.fields:
                col_defs.append(f'"{f.name}" TEXT DEFAULT ""')

            cur.execute(f'CREATE TABLE "{table_name}" ({", ".join(col_defs)})')

            if data:
                field_names = layout.get_field_names()
                cols = ', '.join(f'"{n}"' for n in field_names)
                placeholders = ', '.join('?' for _ in field_names)
                sql = f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders})'

                batch_size = 20_000
                total = len(data)
                # Transação explícita para máxima velocidade (isolation_level=None)
                cur.execute("BEGIN")
                for start in range(0, total, batch_size):
                    batch = data[start:start + batch_size]
                    rows = [[rec.get(n, '') for n in field_names] for rec in batch]
                    cur.executemany(sql, rows)
                    if progress_callback:
                        progress_callback(min(start + batch_size, total), total)
                cur.execute("COMMIT")
            count = cur.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            logger.info(f"Tabela {table_name}: {count} linhas carregadas")
            return count

    def append_to_table(self, table_name: str, data: List[Dict]) -> int:
        """Adiciona linhas a uma tabela já existente."""
        if table_name not in self.loaded_tables:
            raise ValueError(f"Tabela {table_name} não carregada")

        layout = self.loaded_tables[table_name]
        field_names = layout.get_field_names()
        cols = ', '.join(f'"{n}"' for n in field_names)
        placeholders = ', '.join('?' for _ in field_names)
        sql = f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders})'

        with self._lock:
            cur = self.conn.cursor()
            cur.execute("BEGIN")
            rows = [[rec.get(n, '') for n in field_names] for rec in data]
            cur.executemany(sql, rows)
            cur.execute("COMMIT")

        return len(data)

    def get_table_data(self, table_name: str,
                       filters: Optional[Dict[str, str]] = None,
                       limit: Optional[int] = 2000,
                       offset: int = 0) -> Tuple[List[str], List[tuple]]:
        """
        Retorna dados da tabela com filtros opcionais.
        Retorna (colunas, linhas).
        Se ``limit`` for ``None``, retorna todas as linhas que passam pelo filtro
        (sem LIMIT — uso na grade para ajuste em massa).
        """
        where_parts, params = self._build_where(filters)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        if limit is None:
            sql = f'SELECT * FROM "{table_name}" {where_sql}'
            qparams = list(params)
        else:
            sql = f'SELECT * FROM "{table_name}" {where_sql} LIMIT ? OFFSET ?'
            qparams = list(params) + [limit, offset]

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, qparams)
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description] if cur.description else []

        return columns, [tuple(r) for r in rows]

    def count_rows(self, table_name: str,
                   filters: Optional[Dict[str, str]] = None) -> int:
        """Conta registros com filtros opcionais."""
        where_parts, params = self._build_where(filters)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f'SELECT COUNT(*) FROM "{table_name}" {where_sql}'

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, list(params))
            return cur.fetchone()[0]

    def _build_where(self, filters: Optional[Dict[str, str]]) -> Tuple[List[str], List]:
        """
        Constrói cláusula WHERE.
        - Múltiplos campos → AND
        - Mesmo campo com valores separados por | → OR (ex: "100|200|300")
        - Valor entre aspas → igualdade exata (ex: '"NF"')
        - Caso contrário → LIKE %valor%
        """
        parts = []
        params = []
        if not filters:
            return parts, params

        for field, value in filters.items():
            if not value or not value.strip():
                continue

            # Suporte a múltiplos valores OR no mesmo campo (separados por |)
            values = [v.strip() for v in value.split('|') if v.strip()]
            if not values:
                continue

            if len(values) == 1:
                v = values[0]
                # Valor entre aspas = igualdade exata
                if (v.startswith('"') and v.endswith('"')) or \
                   (v.startswith("'") and v.endswith("'")):
                    exact = v[1:-1]
                    parts.append(f'LOWER("{field}") = LOWER(?)')
                    params.append(exact)
                else:
                    parts.append(f'LOWER("{field}") LIKE LOWER(?)')
                    params.append(f'%{v}%')
            else:
                # Múltiplos valores → OR
                or_parts = []
                for v in values:
                    if (v.startswith('"') and v.endswith('"')) or \
                       (v.startswith("'") and v.endswith("'")):
                        exact = v[1:-1]
                        or_parts.append(f'LOWER("{field}") = LOWER(?)')
                        params.append(exact)
                    else:
                        or_parts.append(f'LOWER("{field}") LIKE LOWER(?)')
                        params.append(f'%{v}%')
                parts.append('(' + ' OR '.join(or_parts) + ')')

        return parts, params

    def update_cell(self, table_name: str, row_id: int,
                    field_name: str, new_value: str) -> bool:
        """Atualiza um único campo de uma linha."""
        try:
            with self._lock:
                self.conn.execute(
                    f'UPDATE "{table_name}" SET "{field_name}" = ? WHERE "{ROW_ID_COL}" = ?',
                    [new_value, row_id]
                )
                # isolation_level=None: auto-commit automático, sem COMMIT explícito
                # (exceto em transação manual, onde o usuário controla)
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar célula: {e}")
            return False

    def update_cells_bulk(self, table_name: str,
                          updates: List[Tuple[int, str, str]]) -> int:
        """Atualiza múltiplas células. updates = [(row_id, field, value), ...]"""
        count = 0
        with self._lock:
            # Em autocommit (isolation_level=None), agrupamos em transação para velocidade
            if not self._in_manual_transaction:
                self.conn.execute("BEGIN")
            for row_id, field_name, value in updates:
                try:
                    self.conn.execute(
                        f'UPDATE "{table_name}" SET "{field_name}" = ? WHERE "{ROW_ID_COL}" = ?',
                        [value, row_id]
                    )
                    count += 1
                except Exception as e:
                    logger.error(f"Erro bulk update: {e}")
            if not self._in_manual_transaction:
                self.conn.execute("COMMIT")
        return count

    def execute_sql(self, sql: str) -> Tuple[List[str], List[tuple], str]:
        """
        Executa SQL livre.
        Retorna (colunas, linhas, mensagem).
        - SELECT/EXPLAIN: retorna dados nas colunas/linhas.
        - DML (UPDATE/INSERT/DELETE): executa e retorna mensagem em [2].
        - BEGIN/COMMIT/ROLLBACK: delega para métodos de controle de transação.
        - Sem auto-commit quando _in_manual_transaction estiver ativo.
        """
        sql_strip = sql.strip().rstrip(';').strip()
        if not sql_strip:
            return [], [], 'SQL vazio'

        sql_head = strip_leading_sql_line_comments(sql_strip)
        upper = sql_head.upper()

        # Controle de transação via SQL
        if upper == 'BEGIN' or upper.startswith('BEGIN '):
            _, msg = self.begin()
            return [], [], msg
        if upper == 'COMMIT':
            _, msg = self.commit()
            return [], [], msg
        if upper == 'ROLLBACK':
            _, msg = self.rollback()
            return [], [], msg

        try:
            with self._lock:
                cur = self.conn.cursor()

                # Múltiplas instruções separadas por ;
                stmts = [s.strip() for s in sql_strip.split(';') if s.strip()]
                if len(stmts) > 1:
                    return self._execute_multi(stmts)

                cur.execute(sql_strip)

                # Usar description: comentários ``--`` antes do SELECT quebravam startswith('SELECT')
                if cur.description is not None:
                    rows = cur.fetchall()
                    cols = [d[0] for d in cur.description]
                    return cols, [tuple(r) for r in rows], ''
                tx_note = " [transacao pendente - use COMMIT ou Rollback]" \
                    if self._in_manual_transaction else ""
                first_tok = upper.split(None, 1)[0] if upper else ''
                if first_tok in (
                        'CREATE', 'DROP', 'ALTER', 'REINDEX', 'VACUUM',
                        'ANALYZE', 'ATTACH', 'DETACH'):
                    return [], [], f'OK: DDL executado com sucesso.{tx_note}'
                affected = cur.rowcount if cur.rowcount >= 0 else 0
                msg = f'OK: {affected} linha(s) afetada(s){tx_note}'
                return [], [], msg

        except sqlite3.Error as e:
            return [], [], format_sqlite_error(e)

    def _execute_multi(self, stmts: List[str]) -> Tuple[List[str], List[tuple], str]:
        """Executa múltiplas instruções SQL em sequência."""
        last_cols: List[str] = []
        last_rows: List[tuple] = []
        messages = []

        for stmt in stmts:
            stmt_head = strip_leading_sql_line_comments(stmt)
            upper = stmt_head.upper()
            if upper == 'BEGIN' or upper.startswith('BEGIN '):
                _, msg = self.begin()
                messages.append(msg)
            elif upper == 'COMMIT':
                _, msg = self.commit()
                messages.append(msg)
            elif upper == 'ROLLBACK':
                _, msg = self.rollback()
                messages.append(msg)
            else:
                try:
                    cur = self.conn.cursor()
                    cur.execute(stmt)
                    if cur.description is not None:
                        last_rows = [tuple(r) for r in cur.fetchall()]
                        last_cols = [d[0] for d in cur.description]
                        messages.append(f'SELECT: {len(last_rows)} linha(s)')
                    else:
                        tx_note = " [pendente]" if self._in_manual_transaction else ""
                        st_upper = stmt_head.upper()
                        first_tok = st_upper.split(None, 1)[0] if st_upper else ''
                        if first_tok in (
                                'CREATE', 'DROP', 'ALTER', 'REINDEX', 'VACUUM',
                                'ANALYZE', 'ATTACH', 'DETACH'):
                            messages.append(
                                f'OK: DDL executado com sucesso.{tx_note}')
                        else:
                            affected = cur.rowcount if cur.rowcount >= 0 else 0
                            messages.append(
                                f'OK: {affected} linha(s) afetada(s){tx_note}')
                except sqlite3.Error as e:
                    messages.append(format_sqlite_error(e))

        summary = ' | '.join(messages)
        if last_cols:
            return last_cols, last_rows, summary
        return [], [], summary

    @staticmethod
    def _normalize_sql_table_ident(raw: str) -> str:
        t = raw.strip()
        if t.startswith('"') and t.endswith('"') and len(t) >= 2:
            t = t[1:-1]
        elif t.startswith('`') and t.endswith('`') and len(t) >= 2:
            t = t[1:-1]
        elif t.startswith('[') and t.endswith(']') and len(t) >= 2:
            t = t[1:-1]
        return t.strip()

    def _resolve_physical_table_locked(self, t: str) -> Optional[str]:
        """Resolve nome → tabela SQLite; chamar só com ``self._lock`` adquirido."""
        if not t:
            return None
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND lower(name) = lower(?)",
            (t,),
        ).fetchone()
        if row:
            return str(row[0])
        tl = t.lower()
        pref = [n for n in self._external_tables if n.lower().startswith(tl)]
        if len(pref) == 1:
            return pref[0]
        pref2 = [n for n in self._external_tables if tl.startswith(n.lower())]
        if len(pref2) == 1:
            return pref2[0]
        return None

    def resolve_sql_table_name(self, raw: str) -> Optional[str]:
        """
        Resolve um identificador escrito no SQL ao nome físico da tabela no SQLite.
        Útil para JOIN com tabelas externas (case-insensitive e prefixo único).
        """
        t = self._normalize_sql_table_ident(raw)
        if not t:
            return None
        with self._lock:
            return self._resolve_physical_table_locked(t)

    def get_table_columns(self, table_name: str) -> List[str]:
        """Lista colunas (sem _row_id). Externas usam layout temporário da importação."""
        with self._lock:
            t = self._normalize_sql_table_ident(table_name)
            if not t:
                return []
            phys = self._resolve_physical_table_locked(t) or t
            schema = self._external_schemas.get(phys)
            if schema is None:
                for k, v in self._external_schemas.items():
                    if k.lower() == phys.lower():
                        schema = v
                        break
            if schema is not None:
                return list(schema)
            cur = self.conn.cursor()
            cur.execute(f'PRAGMA table_info("{phys}")')
            cols = [row[1] for row in cur.fetchall() if row[1] != ROW_ID_COL]
        return cols

    def build_external_join_example_sql(
        self, safx_table: str, ext_table: str, ext_columns: List[str],
    ) -> str:
        """
        Exemplo de INNER JOIN: igualdades apenas entre colunas que existem
        na SAFX e na externa (reduz linhas espúrias por cruzamento incompleto).
        """
        try:
            safx_cols = set(self.get_table_columns(safx_table))
        except Exception:
            safx_cols = set()
        ext_set = {c for c in (ext_columns or []) if c and c != ROW_ID_COL}
        common: List[str] = []
        priority = (
            'COD_EMPRESA', 'COD_ESTAB', 'NUM_DOCFIS', 'SERIE_DOCF',
            'DATA_FISCAL', 'COD_DOCTO', 'IND_FIS_JUR', 'COD_FIS_JUR',
        )
        for p in priority:
            if p in safx_cols and p in ext_set and p not in common:
                common.append(p)
        for c in sorted(safx_cols & ext_set):
            if c not in common:
                common.append(c)
        if common:
            on_sql = ' AND\n  '.join(f's."{c}" = e."{c}"' for c in common)
        else:
            c0 = next(iter(ext_set), 'COL_0')
            on_sql = f's.COD_ESTAB = e."{c0}"'
        return (
            f"\n-- Tabela externa «{ext_table}» ({len(ext_columns)} colunas)\n"
            f"-- INNER JOIN: só retorna linhas em que todas as igualdades do ON batem "
            f"na SAFX e na externa.\n"
            f"-- Nunca iguale a mesma coluna do mesmo alias (ex.: s.X = s.X é sempre "
            f"verdade e ignora a tabela externa).\n"
            f"SELECT s.*, e.*\n"
            f'FROM "{safx_table}" s\n'
            f'INNER JOIN "{ext_table}" e\n'
            f'  ON {on_sql}\n'
            f"LIMIT 100;\n"
        )

    def get_row_by_id(self, table_name: str, row_id: int) -> Optional[Dict]:
        """Retorna um registro pelo row_id."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(f'SELECT * FROM "{table_name}" WHERE "{ROW_ID_COL}" = ?', [row_id])
            row = cur.fetchone()
            if row:
                return dict(zip([d[0] for d in cur.description], tuple(row)))
        return None

    def get_rows_by_ids(self, table_name: str,
                        row_ids: List[int]) -> Tuple[List[str], List[tuple]]:
        """Retorna registros pelos row_ids, na mesma ordem da lista (sem duplicar)."""
        if not row_ids:
            return [], []
        ordered: List[int] = []
        seen = set()
        for rid in row_ids:
            try:
                ir = int(rid)
            except (TypeError, ValueError):
                continue
            if ir not in seen:
                seen.add(ir)
                ordered.append(ir)
        if not ordered:
            return [], []
        placeholders = ','.join('?' for _ in ordered)
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                f'SELECT * FROM "{table_name}" WHERE "{ROW_ID_COL}" IN ({placeholders})',
                ordered,
            )
            fetched = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        try:
            rid_idx = cols.index(ROW_ID_COL)
        except ValueError:
            return cols, [tuple(r) for r in fetched]
        by_id = {tuple(r)[rid_idx]: tuple(r) for r in fetched}
        rows_ordered = [by_id[i] for i in ordered if i in by_id]
        return cols, rows_ordered

    def drop_table(self, table_name: str):
        """Remove tabela do banco (SAFX ou externa) e layout temporário associado."""
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
        with self._lock:
            self.loaded_tables.pop(table_name, None)
            self._external_tables.discard(safe)
            self._external_schemas.pop(safe, None)
            try:
                self.conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                self.conn.execute("COMMIT")
            except Exception as e:
                logger.error(f"Erro ao remover tabela {table_name}: {e}")

    def get_loaded_tables(self) -> List[str]:
        return list(self.loaded_tables.keys())

    def list_sqlite_user_tables(self) -> List[str]:
        """Tabelas de utilizador no ficheiro SQLite (exclui internas ``sqlite_*``)."""
        with self._lock:
            cur = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND substr(name,1,7) != 'sqlite_' ORDER BY name COLLATE NOCASE"
            )
            return [str(r[0]) for r in cur.fetchall()]

    def get_tables_for_sql_panel(self) -> List[str]:
        """
        Lista para o combo do editor SQL: SAFX na ordem de carga,
        depois outras tabelas físicas (ex.: ``CREATE TABLE … AS SELECT`` para backup).
        """
        out: List[str] = []
        seen: Set[str] = set()
        for name in self.get_loaded_tables():
            out.append(name)
            seen.add(name)
        for name in self.list_sqlite_user_tables():
            if name not in seen:
                out.append(name)
                seen.add(name)
        return out

    def get_schema_info(self, table_name: str) -> List[Dict]:
        """Retorna informações de esquema da tabela."""
        layout = self.loaded_tables.get(table_name)
        if layout:
            result = []
            for f in layout.fields:
                info = {
                    'campo': f.name,
                    'tipo': f.field_type,
                    'tamanho': f.size_str,
                    'obrigatorio': 'SIM' if f.is_mandatory else 'NÃO',
                    'descricao': f.description[:60] + ('...' if len(f.description) > 60 else '')
                }
                result.append(info)
            return result
        # Tabela externa / sem layout SAFX: colunas via PRAGMA
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(f'PRAGMA table_info("{table_name}")')
            prag = cur.fetchall()
        result = []
        for row in prag:
            _cid, name, ctype, _notnull, _dflt, _pk = row
            if name == ROW_ID_COL:
                continue
            result.append({
                'campo': name,
                'tipo': ctype or 'TEXT',
                'tamanho': '',
                'obrigatorio': 'NÃO',
                'descricao': 'layout temporário (planilha externa)',
            })
        return result
