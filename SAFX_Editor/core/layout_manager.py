"""
Gerenciador de Layouts SAFX.
Lê os arquivos MD do MANUAL LAYOUT para obter definições de campos.
"""
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


@dataclass
class FieldDefinition:
    item: int
    name: str
    field_type: str      # 'alfa', 'num', 'date'
    size_str: str        # tamanho original ex: "003", "014V002"
    size: int            # tamanho principal
    decimals: int        # casas decimais (0 se nenhuma)
    is_mandatory: bool
    description: str

    @classmethod
    def from_parts(cls, item: int, name: str, type_str: str,
                   size_str: str, mandatory_str: str, desc: str) -> 'FieldDefinition':
        type_lower = type_str.lower()
        if 'numer' in type_lower or 'number' in type_lower or 'n)' in type_lower:
            ftype = 'num'
        elif 'data' in type_lower or 'date' in type_lower:
            ftype = 'date'
        else:
            ftype = 'alfa'

        size_clean = size_str.strip().replace(' ', '')
        size = 0
        decimals = 0
        if 'V' in size_clean.upper():
            parts = size_clean.upper().split('V')
            try:
                size = int(re.sub(r'\D', '', parts[0])) if parts[0] else 0
                decimals = int(re.sub(r'\D', '', parts[1])) if parts[1] else 0
            except (ValueError, IndexError):
                size = 255
        else:
            digits = re.sub(r'\D', '', size_clean)
            size = int(digits) if digits else 255

        is_mandatory = mandatory_str.strip().upper() in ('SIM', 'YES', 'S', 'Y', 'TRUE', '1')

        return cls(
            item=item,
            name=name.strip(),
            field_type=ftype,
            size_str=size_str.strip(),
            size=size,
            decimals=decimals,
            is_mandatory=is_mandatory,
            description=desc.strip()
        )


@dataclass
class TableLayout:
    table_name: str
    bank_table: str
    fields: List[FieldDefinition] = field(default_factory=list)

    def get_field(self, name: str) -> Optional[FieldDefinition]:
        name_upper = name.upper()
        for f in self.fields:
            if f.name.upper() == name_upper:
                return f
        return None

    def get_field_names(self) -> List[str]:
        return [f.name for f in self.fields]

    def get_mandatory_fields(self) -> List[str]:
        return [f.name for f in self.fields if f.is_mandatory]


class LayoutManager:
    """Gerencia layouts de tabelas SAFX lidos dos arquivos MD."""

    def __init__(self, layout_dir: str):
        self.layout_dir = Path(layout_dir)
        self._cache: Dict[str, TableLayout] = {}

    def get_available_tables(self) -> List[str]:
        """Retorna lista de tabelas disponíveis no diretório de layouts."""
        tables = []
        if not self.layout_dir.exists():
            logger.warning(f"Layout dir não encontrado: {self.layout_dir}")
            return tables
        for f in sorted(self.layout_dir.glob("SAFX*.md")):
            tables.append(f.stem.upper())
        return tables

    def get_layout(self, table_name: str) -> Optional[TableLayout]:
        """Retorna o layout da tabela, com cache."""
        key = table_name.upper()
        if key in self._cache:
            return self._cache[key]

        md_path = self.layout_dir / f"{key}.md"
        if not md_path.exists():
            # Tenta variações
            for f in self.layout_dir.glob(f"{key}*.md"):
                md_path = f
                break
            else:
                logger.warning(f"Layout não encontrado para: {table_name}")
                return None

        layout = self._parse_md_file(md_path, key)
        if layout:
            self._cache[key] = layout
        return layout

    def _parse_md_file(self, filepath: Path, table_name: str) -> Optional[TableLayout]:
        """Parseia arquivo MD do MANUAL LAYOUT."""
        try:
            content = filepath.read_text(encoding='utf-8', errors='replace')

            # Extrai nome da tabela no banco
            bank_table = table_name
            m = re.search(r'\*\*Tabela no Banco:\*\*\s*`?([^`\n]+)`?', content)
            if m:
                bank_table = m.group(1).strip()

            fields = []

            # Padrão para linhas da tabela de campos:
            # | 01 | `COD_EMPRESA` | Alfanumérico (VARCHAR2) | 003 | SIM | Código da Empresa
            row_pat = re.compile(
                r'^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|\n]+)',
                re.MULTILINE
            )

            for m in row_pat.finditer(content):
                item_num = int(m.group(1))
                field_name = m.group(2).strip()
                type_str = m.group(3).strip()
                size_str = m.group(4).strip()
                mandatory_str = m.group(5).strip()
                desc = m.group(6).strip()

                # Ignora linhas de cabeçalho
                if field_name.lower() in ('campo', 'field', 'nome', 'name'):
                    continue

                fd = FieldDefinition.from_parts(
                    item_num, field_name, type_str,
                    size_str, mandatory_str, desc
                )
                fields.append(fd)

            # Formato alternativo (ESTRUTURA/estrutura_md — tabela GitHub sem backticks)
            if not fields:
                fields = self._parse_md_github_table(content)

            # Remove duplicatas (mesmo campo)
            seen = set()
            unique_fields = []
            for f in fields:
                if f.name not in seen:
                    seen.add(f.name)
                    unique_fields.append(f)

            if not unique_fields:
                logger.warning(f"Nenhum campo encontrado em {filepath}")
                return None

            return TableLayout(
                table_name=table_name,
                bank_table=bank_table,
                fields=unique_fields
            )

        except Exception as e:
            logger.error(f"Erro ao parsear {filepath}: {e}")
            return None

    def _parse_md_github_table(self, content: str) -> List[FieldDefinition]:
        """
        Formato de tabela Markdown usado em ESTRUTURA/estrutura_md, ex.:
        | Campo | Tipo | Tamanho | Precisão | Escala | Nulo | ID | Padrão |
        | COD_EMPRESA | VARCHAR2 | 3 | - | - | ✓ | 1 | - |
        | SEQ_ARQ | NUMBER | 22 | 20.0 | 0.0 | ✓ | 147 | - |
        """
        fields: List[FieldDefinition] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith('|'):
                continue
            inner = stripped[1:-1] if stripped.endswith('|') else stripped[1:]
            cells = [c.strip() for c in inner.split('|')]
            if len(cells) < 3:
                continue
            col0 = cells[0]
            if not col0 or set(col0) <= {'-', ':', ' '}:
                continue
            if col0.lower() in ('campo', 'field', 'nome', 'name'):
                continue
            name = col0
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
                continue

            type_str = cells[1] if len(cells) > 1 else 'VARCHAR2'
            size_cell = cells[2] if len(cells) > 2 else '50'
            prec = cells[3] if len(cells) > 3 else '-'
            scale = cells[4] if len(cells) > 4 else '-'
            nulo = cells[5] if len(cells) > 5 else ''
            item_raw = cells[6] if len(cells) > 6 else '0'
            try:
                item_num = int(float(item_raw))
            except ValueError:
                item_num = len(fields) + 1

            def _norm_dash(s: str) -> str:
                return (s or '').replace('−', '-').replace('—', '-').strip()

            prec = _norm_dash(prec)
            scale = _norm_dash(scale)

            typ_u = type_str.upper()
            if typ_u == 'NUMBER' and prec not in ('-', '') and scale not in ('-', ''):
                try:
                    sz = int(float(size_cell))
                    sc = int(float(scale))
                    size_str = f"{sz:03d}V{sc:03d}"
                except ValueError:
                    size_str = str(size_cell).strip()
            else:
                try:
                    sz = int(float(size_cell))
                    size_str = str(sz)
                except ValueError:
                    size_str = (size_cell or '50').strip()

            # Coluna "Nulo": ✓ costuma indicar que aceita NULL (campo não obrigatório).
            n_st = (nulo or '').strip()
            if '✓' in n_st or '√' in n_st or '✔' in n_st:
                mandatory_str = 'NÃO'
            elif n_st.upper() in ('N', 'NÃO', 'NAO', 'NO'):
                mandatory_str = 'SIM'
            else:
                mandatory_str = 'NÃO'

            desc = name
            fd = FieldDefinition.from_parts(
                item_num, name, type_str, size_str, mandatory_str, desc
            )
            fields.append(fd)

        return fields

    def clear_cache(self):
        self._cache.clear()


# Campos chave padrão por tabela (configurável pelo usuário)
DEFAULT_KEY_FIELDS: Dict[str, List[str]] = {
    "SAFX07": ["COD_EMPRESA", "COD_ESTAB", "DATA_SAIDA_REC", "MOVTO_E_S",
               "NORM_DEV", "COD_DOCTO", "IDENT_FIS_JUR", "COD_FIS_JUR",
               "NUM_DOCFIS", "SERIE_DOCFIS"],
    "SAFX08": ["COD_EMPRESA", "COD_ESTAB", "DATA_FISCAL", "MOVTO_E_S",
               "NORM_DEV", "COD_DOCTO", "IND_FIS_JUR", "COD_FIS_JUR",
               "NUM_DOCFIS", "SERIE_DOCFIS", "NUM_ITEM", "COD_PRODUTO"],
    "SAFX04": ["COD_EMPRESA", "IND_FIS_JUR", "COD_FIS_JUR"],
    "SAFX05": ["COD_EMPRESA", "COD_ESTAB", "DATA_FISCAL", "MOVTO_E_S",
               "NORM_DEV", "COD_DOCTO", "IND_FIS_JUR", "COD_FIS_JUR",
               "NUM_DOCFIS", "SERIE_DOCFIS", "NUM_ITEM", "COD_TRIBUTO",
               "COD_SITUACAO_TRIB"],
    "SAFX01": ["COD_EMPRESA", "COD_ESTAB", "DATA_OPERACAO", "NUM_LANCAMENTO",
               "CONTA_DEB_CRED"],
    "SAFX14": ["COD_EMPRESA", "COD_ESTAB", "DATA_FISCAL", "MOVTO_E_S",
               "NORM_DEV", "COD_DOCTO", "IND_FIS_JUR", "COD_FIS_JUR",
               "NUM_DOCFIS", "SERIE_DOCFIS", "NUM_ITEM"],
    "SAFX21": ["COD_EMPRESA", "COD_ESTAB", "DATA_FISCAL", "MOVTO_E_S",
               "NORM_DEV", "COD_DOCTO", "IND_FIS_JUR", "COD_FIS_JUR",
               "NUM_DOCFIS", "SERIE_DOCFIS"],
}
