"""
Exportador de dados SAFX para formato CSV homologado (MS-DOS ; separado).

Regras do formato homologado:
- Separador: ;
- Encoding: latin-1 (ANSI Windows)
- Linha 1: cabeçalho com nomes dos campos
- Colunas: TABELA | ACAO | [CAMPOS CHAVE] | [CAMPOS ALTERADOS]
- Datas: YYYYMMDD (sem separadores)
- Números: sem separador de decimal (ex: 14v2 → integer sem vírgula)
- Valores texto: trimados, sem aspas
- Sem BOM
"""
import csv
import logging
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from .layout_manager import LayoutManager, FieldDefinition, TableLayout

logger = logging.getLogger(__name__)


def _strip_decimal_separator(value: str) -> str:
    """
    Remove separador decimal de valores numéricos.
    Exemplos:
      499076,29  → 49907629
      499076.29  → 49907629
      49907629   → 49907629 (já ok)
    """
    v = value.strip()
    if not v:
        return v
    # Detecta se tem separador decimal
    # Vírgula brasileira: 499.076,29 → 49907629
    # Ponto americano: 499076.29 → 49907629
    # Remove pontos de milhar e converte vírgula decimal para nada
    if ',' in v:
        # Formato brasileiro: 1.234.567,89
        clean = v.replace('.', '').replace(',', '')
        return clean
    elif '.' in v:
        # Formato americano: 1234567.89
        clean = v.replace('.', '')
        return clean
    return v


def _format_value_for_export(value: str,
                              field_def: Optional[FieldDefinition]) -> str:
    """Formata valor conforme regras do formato homologado."""
    if value is None:
        value = ''
    value = str(value).strip()

    if not field_def:
        return value

    if field_def.field_type == 'num' and field_def.decimals > 0:
        # Número com casas decimais → remove separador
        return _strip_decimal_separator(value)

    if field_def.field_type == 'date':
        # Data → YYYYMMDD (remove traços/barras se houver)
        date_clean = re.sub(r'[-/.]', '', value)
        return date_clean[:8] if date_clean else value

    # Alfanumérico: retorna limpo
    return value


class SAFXExporter:
    """Exporta dados SAFX no formato CSV homologado."""

    def __init__(self, layout_manager: LayoutManager):
        self.layout_manager = layout_manager

    def export(self, table_name: str,
               action: str,
               key_fields: List[str],
               change_fields: List[str],
               columns: List[str],
               rows: List[tuple],
               output_path: str) -> Tuple[int, str]:
        """
        Exporta linhas para arquivo CSV homologado.

        Args:
            table_name: Nome da tabela (ex: SAFX07)
            action: UPDATE | INSERT | DELETE
            key_fields: Campos chave (identificam o registro)
            change_fields: Campos alterados (valores a modificar)
            columns: Lista de colunas conforme retornado do banco
            rows: Tuplas de dados
            output_path: Caminho do arquivo de saída

        Returns:
            (num_linhas, mensagem)
        """
        layout = self.layout_manager.get_layout(table_name)

        # Mapeia nome de coluna → índice na tupla
        col_idx = {col: i for i, col in enumerate(columns)}

        # Cabeçalho: TABELA;ACAO;[chaves];[alterados]
        header = ['TABELA', 'ACAO'] + key_fields + change_fields

        try:
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', newline='', encoding='latin-1') as f:
                # Cabeçalho com ; no final (formato homologado exige trailing ;)
                f.write(';'.join(header) + ';\r\n')

                for row in rows:
                    line_values = [table_name, action]

                    for fname in key_fields:
                        val = self._get_value(row, col_idx, fname)
                        fd = layout.get_field(fname) if layout else None
                        line_values.append(_format_value_for_export(val, fd))

                    for fname in change_fields:
                        val = self._get_value(row, col_idx, fname)
                        fd = layout.get_field(fname) if layout else None
                        line_values.append(_format_value_for_export(val, fd))

                    # Cada linha de dados também termina com ;
                    f.write(';'.join(line_values) + ';\r\n')

            count = len(rows)
            msg = f'OK: {count} linha(s) exportada(s) para:\n{output_path}'
            logger.info(f"Exportado {count} linhas: {output_path}")
            return count, msg

        except Exception as e:
            msg = f'Erro ao exportar: {e}'
            logger.error(msg)
            return 0, msg

    def export_full_safx(self, table_name: str,
                         columns: List[str],
                         rows: List[tuple],
                         output_path: str,
                         encoding: str = 'latin-1') -> Tuple[int, str]:
        """
        Exporta a tabela COMPLETA no mesmo formato tab-separado que foi importada.
        Útil quando o cliente não quer usar UPDATE/INSERT mas subir os dados no padrão original.
        """
        layout = self.layout_manager.get_layout(table_name)
        col_idx = {col: i for i, col in enumerate(columns)}

        # Remove _row_id da saída
        export_cols = [c for c in columns if not c.startswith('_')]

        try:
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', newline='', encoding=encoding) as f:
                for row in rows:
                    values = []
                    for fname in export_cols:
                        idx = col_idx.get(fname)
                        val = str(row[idx]) if idx is not None and row[idx] is not None else ''
                        fd = layout.get_field(fname) if layout else None
                        values.append(_format_value_for_export(val, fd))
                    # Formato original: tab-separado, terminando com \r\n
                    f.write('\t'.join(values) + '\r\n')

            count = len(rows)
            return count, f'OK: {count} linha(s) exportada(s) → {output_path}'
        except Exception as e:
            return 0, f'Erro: {e}'

    def preview_full_safx(self, table_name: str,
                          columns: List[str],
                          rows: List[tuple],
                          max_preview: int = 5) -> str:
        """Preview do formato SAFX original (tab-separado)."""
        layout = self.layout_manager.get_layout(table_name)
        col_idx = {col: i for i, col in enumerate(columns)}
        export_cols = [c for c in columns if not c.startswith('_')]

        lines = ['\t'.join(export_cols)]
        for row in rows[:max_preview]:
            values = []
            for fname in export_cols:
                idx = col_idx.get(fname)
                val = str(row[idx]) if idx is not None and row[idx] is not None else ''
                fd = layout.get_field(fname) if layout else None
                values.append(_format_value_for_export(val, fd))
            lines.append('\t'.join(values))
        return '\n'.join(lines)

    def _get_value(self, row: tuple, col_idx: Dict[str, int], fname: str) -> str:
        """Obtém valor de uma linha pelo nome do campo."""
        idx = col_idx.get(fname)
        if idx is None:
            return ''
        val = row[idx]
        return str(val) if val is not None else ''

    def preview(self, table_name: str,
                action: str,
                key_fields: List[str],
                change_fields: List[str],
                columns: List[str],
                rows: List[tuple],
                max_preview: int = 10) -> str:
        """Retorna preview do CSV como string (sem salvar em arquivo)."""
        layout = self.layout_manager.get_layout(table_name)
        col_idx = {col: i for i, col in enumerate(columns)}

        lines = []
        header = ['TABELA', 'ACAO'] + key_fields + change_fields
        # Cabeçalho e linhas terminam com ; (formato homologado)
        lines.append(';'.join(header) + ';')

        for row in rows[:max_preview]:
            vals = [table_name, action]
            for fname in key_fields:
                val = self._get_value(row, col_idx, fname)
                fd = layout.get_field(fname) if layout else None
                vals.append(_format_value_for_export(val, fd))
            for fname in change_fields:
                val = self._get_value(row, col_idx, fname)
                fd = layout.get_field(fname) if layout else None
                vals.append(_format_value_for_export(val, fd))
            lines.append(';'.join(vals) + ';')

        if len(rows) > max_preview:
            lines.append(f'... ({len(rows) - max_preview} linha(s) adicionais)')

        return '\n'.join(lines)
