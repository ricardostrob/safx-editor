"""
Banco de dados SQLite in-memory para armazenamento temporário de SAFX.
Os dados NÃO são persistidos - servem apenas para manipulação e ajustes.
"""
import sqlite3
import logging
import threading
import datetime as _dt
from typing import List, Dict, Tuple, Optional, Any

from .layout_manager import TableLayout

logger = logging.getLogger(__name__)

# Coluna interna de controle de linha
ROW_ID_COL = '_row_id'


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
        self._external_tables: set = set()   # tabelas externas (Excel/CSV importados)

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

    # ─── Tabelas externas (Excel / CSV para JOIN) ────────────────────────────

    def import_external_table(self, table_name: str,
                              columns: List[str],
                              rows: List[List],
                              progress_cb=None) -> int:
        """
        Cria (ou substitui) uma tabela temporária no SQLite com dados externos
        (Excel, CSV...). Retorna número de linhas importadas.
        """
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
        safe_cols = [''.join(c if c.isalnum() or c == '_' else '_' for c in str(col))
                     for col in columns]

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(f'DROP TABLE IF EXISTS "{safe}"')
            cols_def = ', '.join(f'"{c}" TEXT' for c in safe_cols)
            cur.execute(f'CREATE TABLE "{safe}" ({cols_def})')

            batch_size = 5_000
            total = 0
            buf = []
            placeholders = ','.join('?' * len(safe_cols))

            for row in rows:
                padded = list(row) + [''] * max(0, len(safe_cols) - len(row))
                buf.append([str(v) if v is not None else '' for v in padded[:len(safe_cols)]])
                total += 1
                if len(buf) >= batch_size:
                    cur.executemany(
                        f'INSERT INTO "{safe}" VALUES ({placeholders})', buf)
                    buf.clear()
                    if progress_cb:
                        progress_cb(total)

            if buf:
                cur.executemany(
                    f'INSERT INTO "{safe}" VALUES ({placeholders})', buf)
            self.conn.commit()

        # Registra como tabela externa
        self._external_tables.add(safe)
        return total

    def drop_external_table(self, table_name: str):
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
        with self._lock:
            self.conn.execute(f'DROP TABLE IF EXISTS "{safe}"')
            self.conn.commit()
        self._external_tables.discard(safe)

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
                       limit: int = 2000,
                       offset: int = 0) -> Tuple[List[str], List[tuple]]:
        """
        Retorna dados da tabela com filtros opcionais.
        Retorna (colunas, linhas).
        """
        where_parts, params = self._build_where(filters)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f'SELECT * FROM "{table_name}" {where_sql} LIMIT ? OFFSET ?'
        params = list(params) + [limit, offset]

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
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

        upper = sql_strip.upper()

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

                if (upper.startswith('SELECT') or upper.startswith('EXPLAIN')
                        or upper.startswith('WITH') or upper.startswith('PRAGMA')):
                    rows = cur.fetchall()
                    cols = [d[0] for d in cur.description] if cur.description else []
                    return cols, [tuple(r) for r in rows], ''
                else:
                    # DML com isolation_level=None: auto-commit automático
                    # Só precisamos de COMMIT explícito se estiver em transação manual
                    # (caso contrário cada stmt já commitou automaticamente)
                    affected = cur.rowcount if cur.rowcount >= 0 else 0
                    tx_note = " [transacao pendente - use COMMIT ou Rollback]" \
                        if self._in_manual_transaction else ""
                    msg = f'OK: {affected} linha(s) afetada(s){tx_note}'
                    return [], [], msg

        except sqlite3.Error as e:
            return [], [], f'Erro SQL: {e}'

    def _execute_multi(self, stmts: List[str]) -> Tuple[List[str], List[tuple], str]:
        """Executa múltiplas instruções SQL em sequência."""
        last_cols: List[str] = []
        last_rows: List[tuple] = []
        messages = []

        for stmt in stmts:
            upper = stmt.upper()
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
                    if (upper.startswith('SELECT') or upper.startswith('EXPLAIN')
                            or upper.startswith('WITH') or upper.startswith('PRAGMA')):
                        last_rows = [tuple(r) for r in cur.fetchall()]
                        last_cols = [d[0] for d in cur.description] if cur.description else []
                        messages.append(f'SELECT: {len(last_rows)} linha(s)')
                    else:
                        affected = cur.rowcount if cur.rowcount >= 0 else 0
                        tx_note = " [pendente]" if self._in_manual_transaction else ""
                        messages.append(f'OK: {affected} linha(s) afetada(s){tx_note}')
                except sqlite3.Error as e:
                    messages.append(f'Erro: {e}')

        summary = ' | '.join(messages)
        if last_cols:
            return last_cols, last_rows, summary
        return [], [], summary

    def get_table_columns(self, table_name: str) -> List[str]:
        """Retorna lista de colunas da tabela (sem _row_id)."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(f'PRAGMA table_info("{table_name}")')
            cols = [row[1] for row in cur.fetchall() if row[1] != ROW_ID_COL]
        return cols

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
        """Retorna registros específicos pelos row_ids."""
        if not row_ids:
            return [], []
        placeholders = ','.join('?' for _ in row_ids)
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                f'SELECT * FROM "{table_name}" WHERE "{ROW_ID_COL}" IN ({placeholders})',
                row_ids
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [tuple(r) for r in rows]

    def drop_table(self, table_name: str):
        """Remove tabela do banco."""
        with self._lock:
            self.loaded_tables.pop(table_name, None)
            try:
                self.conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                self.conn.execute("COMMIT")
            except Exception as e:
                logger.error(f"Erro ao remover tabela {table_name}: {e}")

    def get_loaded_tables(self) -> List[str]:
        return list(self.loaded_tables.keys())

    def get_schema_info(self, table_name: str) -> List[Dict]:
        """Retorna informações de esquema da tabela."""
        layout = self.loaded_tables.get(table_name)
        if not layout:
            return []
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
