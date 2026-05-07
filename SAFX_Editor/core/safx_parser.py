"""
Parser de arquivos TXT SAFX.
Arquivos SAFX são separados por TAB, com campos alinhados por espaços.
"""
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Iterator

from .layout_manager import LayoutManager, TableLayout

logger = logging.getLogger(__name__)

NULL_MARKERS = {'@', '@ ', '@  ', '@   ', '@    '}


def _clean_value(raw: str) -> str:
    """Limpa valor de campo SAFX: remove espaços extras e marcadores nulos."""
    v = raw.strip()
    if v == '@' or v.startswith('@') and v[1:].strip() == '':
        return ''
    return v


class SAFXParser:
    """Parser de arquivos TXT SAFX (separados por TAB)."""

    def __init__(self, layout_manager: LayoutManager):
        self.layout_manager = layout_manager

    @staticmethod
    def _clean(raw: str) -> str:
        """Limpa valor de campo (método estático para uso externo)."""
        return _clean_value(raw)

    def detect_table_name(self, filepath: str) -> Optional[str]:
        """Detecta nome da tabela a partir do nome do arquivo."""
        stem = Path(filepath).stem.upper()
        # Pega apenas a parte SAFXNN (ex: SAFX07 de SAFX07_CUMMINS)
        import re
        m = re.match(r'(SAFX\d+)', stem)
        if m:
            return m.group(1)
        return stem if stem.startswith('SAFX') else None

    def count_lines(self, filepath: str) -> int:
        """Conta linhas do arquivo (para arquivos grandes)."""
        count = 0
        try:
            with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
                for _ in f:
                    count += 1
        except Exception:
            count = 0
        return count

    def parse_file(self, filepath: str, table_name: str,
                   max_rows: int = 0,
                   progress_callback=None) -> Tuple[TableLayout, List[Dict]]:
        """
        Parseia arquivo SAFX TXT.
        max_rows=0 significa SEM LIMITE (carrega tudo).
        Retorna (layout, lista_de_registros).
        """
        layout = self.layout_manager.get_layout(table_name)
        if not layout:
            raise ValueError(f"Layout não encontrado para tabela: {table_name}")

        field_names = layout.get_field_names()
        records = []

        try:
            with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
                for line_num, raw_line in enumerate(f):
                    if max_rows and line_num >= max_rows:
                        logger.info(f"Limite de {max_rows} linhas atingido em {filepath}")
                        break

                    line = raw_line.rstrip('\n\r')
                    if not line.strip():
                        continue

                    parts = line.split('\t')
                    record: Dict[str, str] = {
                        fname: (_clean_value(parts[i]) if i < len(parts) else '')
                        for i, fname in enumerate(field_names)
                    }
                    records.append(record)

                    if progress_callback and line_num % 10_000 == 0:
                        progress_callback(line_num)

        except FileNotFoundError:
            raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")
        except Exception as e:
            raise RuntimeError(f"Erro ao ler arquivo: {e}")

        logger.info(f"Carregados {len(records)} registros de {filepath}")
        return layout, records

    def parse_file_chunked(self, filepath: str, table_name: str,
                           chunk_size: int = 10_000) -> Iterator[Tuple[TableLayout, List[Dict]]]:
        """Parser em chunks para arquivos muito grandes."""
        layout = self.layout_manager.get_layout(table_name)
        if not layout:
            raise ValueError(f"Layout não encontrado para: {table_name}")

        field_names = layout.get_field_names()
        chunk: List[Dict] = []

        with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
            for raw_line in f:
                line = raw_line.rstrip('\n\r')
                if not line.strip():
                    continue

                parts = line.split('\t')
                record = {fname: (_clean_value(parts[i]) if i < len(parts) else '')
                          for i, fname in enumerate(field_names)}
                chunk.append(record)

                if len(chunk) >= chunk_size:
                    yield layout, chunk
                    chunk = []

        if chunk:
            yield layout, chunk
