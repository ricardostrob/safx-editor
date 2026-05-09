"""
Banco de dados externo opcional para persistência de dados SAFX.
Suporta: Oracle, PostgreSQL, MySQL, Supabase (PostgreSQL), SQLite local.

Quando configurado, o sistema pode salvar todas as tabelas SAFX e o change log
neste banco. Caso contrário, funciona normalmente em memória (padrão).
"""
import logging
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Scripts DDL para cada banco ────────────────────────────────────────────────

# Campos comuns de uma tabela SAFX genérica
_SAFX_DDL_COMMON = """
-- Cria tabela de configuração de conexões ERP/banco
CREATE TABLE IF NOT EXISTS safx_connections (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    type        VARCHAR(30)  NOT NULL,
    config_json TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cria tabela de log de alterações
CREATE TABLE IF NOT EXISTS safx_change_log (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(50),
    timestamp   VARCHAR(30),
    table_name  VARCHAR(50),
    row_id      INTEGER,
    field_name  VARCHAR(100),
    old_value   TEXT,
    new_value   TEXT,
    source      VARCHAR(30),
    sql_snippet TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cria índices para performance
CREATE INDEX IF NOT EXISTS idx_cl_table ON safx_change_log(table_name);
CREATE INDEX IF NOT EXISTS idx_cl_session ON safx_change_log(session_id);
CREATE INDEX IF NOT EXISTS idx_cl_ts ON safx_change_log(timestamp);
"""

_SAFX_DDL_POSTGRES = """
-- PostgreSQL / Supabase
-- Execute este script no banco antes de conectar o SAFX Editor.

CREATE SCHEMA IF NOT EXISTS safx;

CREATE TABLE IF NOT EXISTS safx.connections (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    type        VARCHAR(30)  NOT NULL,
    config_json JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS safx.change_log (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(50),
    ts          TIMESTAMPTZ DEFAULT NOW(),
    table_name  VARCHAR(50) NOT NULL,
    row_id      INTEGER,
    field_name  VARCHAR(100),
    old_value   TEXT,
    new_value   TEXT,
    source      VARCHAR(30),
    sql_snippet TEXT
);

CREATE INDEX IF NOT EXISTS idx_cl_table ON safx.change_log(table_name);
CREATE INDEX IF NOT EXISTS idx_cl_session ON safx.change_log(session_id);
CREATE INDEX IF NOT EXISTS idx_cl_ts ON safx.change_log(ts);

-- Tabelas SAFX (estrutura genérica — campos adicionados dinamicamente)
-- Cada tabela SAFX terá sua própria tabela no schema safx
-- Exemplo para SAFX07:
--   CREATE TABLE IF NOT EXISTS safx.safx07 (
--       _row_id BIGSERIAL PRIMARY KEY,
--       COD_EMPRESA VARCHAR(10), COD_ESTAB VARCHAR(10), ...
--   );

-- Função para criar tabela SAFX dinamicamente
CREATE OR REPLACE FUNCTION safx.create_safx_table(
    p_table VARCHAR,
    p_columns TEXT[]
) RETURNS void AS $$
DECLARE
    col TEXT;
    ddl TEXT;
BEGIN
    ddl := 'CREATE TABLE IF NOT EXISTS safx.' || lower(p_table) || ' (_row_id BIGSERIAL PRIMARY KEY';
    FOREACH col IN ARRAY p_columns LOOP
        ddl := ddl || ', ' || quote_ident(lower(col)) || ' TEXT DEFAULT ''''';
    END LOOP;
    ddl := ddl || ')';
    EXECUTE ddl;
END;
$$ LANGUAGE plpgsql;

COMMENT ON SCHEMA safx IS 'Schema do SAFX Editor — MasterSAF Data Adjuster | Adejo';
"""

_SAFX_DDL_ORACLE = """
-- Oracle Database
-- Execute este script como DBA ou com privilégios CREATE TABLE/INDEX.

CREATE TABLE safx_change_log (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  VARCHAR2(50),
    ts          TIMESTAMP DEFAULT SYSTIMESTAMP,
    table_name  VARCHAR2(50) NOT NULL,
    row_id      NUMBER,
    field_name  VARCHAR2(100),
    old_value   CLOB,
    new_value   CLOB,
    source      VARCHAR2(30),
    sql_snippet CLOB
);

CREATE INDEX idx_cl_table   ON safx_change_log(table_name);
CREATE INDEX idx_cl_session ON safx_change_log(session_id);
CREATE INDEX idx_cl_ts      ON safx_change_log(ts);

CREATE TABLE safx_connections (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR2(100) NOT NULL,
    conn_type   VARCHAR2(30)  NOT NULL,
    config_json CLOB,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);

-- Nota: cada tabela SAFX deve ser criada separadamente.
-- Exemplo SAFX07:
-- CREATE TABLE safx07 (
--     row_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
--     COD_EMPRESA VARCHAR2(10), COD_ESTAB VARCHAR2(10),
--     DATA_FISCAL VARCHAR2(8), ...
-- );
"""

_SAFX_DDL_MYSQL = """
-- MySQL / MariaDB
-- Execute como root ou com privilégios CREATE DATABASE/TABLE.

CREATE DATABASE IF NOT EXISTS safx_editor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE safx_editor;

CREATE TABLE IF NOT EXISTS change_log (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    session_id  VARCHAR(50),
    ts          DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    table_name  VARCHAR(50) NOT NULL,
    row_id      INT,
    field_name  VARCHAR(100),
    old_value   LONGTEXT,
    new_value   LONGTEXT,
    source      VARCHAR(30),
    sql_snippet LONGTEXT,
    INDEX idx_table (table_name),
    INDEX idx_session (session_id),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS connections (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    conn_type   VARCHAR(30)  NOT NULL,
    config_json JSON,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_SAFX_DDL_SQLITE = """
-- SQLite (arquivo local)
-- Este script é executado automaticamente pelo SAFX Editor ao criar o arquivo.

CREATE TABLE IF NOT EXISTS safx_change_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    ts          TEXT DEFAULT (datetime('now')),
    table_name  TEXT NOT NULL,
    row_id      INTEGER,
    field_name  TEXT,
    old_value   TEXT,
    new_value   TEXT,
    source      TEXT,
    sql_snippet TEXT
);

CREATE INDEX IF NOT EXISTS idx_cl_table   ON safx_change_log(table_name);
CREATE INDEX IF NOT EXISTS idx_cl_session ON safx_change_log(session_id);

CREATE TABLE IF NOT EXISTS safx_connections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    conn_type   TEXT NOT NULL,
    config_json TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Cada tabela SAFX é criada dinamicamente com CREATE TABLE IF NOT EXISTS
"""

DDL_SCRIPTS = {
    'postgres':  _SAFX_DDL_POSTGRES,
    'supabase':  _SAFX_DDL_POSTGRES,
    'oracle':    _SAFX_DDL_ORACLE,
    'mysql':     _SAFX_DDL_MYSQL,
    'sqlite':    _SAFX_DDL_SQLITE,
}

DDL_SCRIPT_NAMES = {
    'postgres':  'safx_setup_postgres.sql',
    'supabase':  'safx_setup_supabase.sql',
    'oracle':    'safx_setup_oracle.sql',
    'mysql':     'safx_setup_mysql.sql',
    'sqlite':    'safx_setup_sqlite.sql',
}


def get_ddl_script(db_type: str) -> str:
    return DDL_SCRIPTS.get(db_type, '-- Tipo não suportado')


def save_ddl_script(db_type: str, output_dir: str) -> str:
    """Salva o script DDL em disco e retorna o caminho."""
    script = get_ddl_script(db_type)
    fname = DDL_SCRIPT_NAMES.get(db_type, f'safx_setup_{db_type}.sql')
    path = Path(output_dir) / fname
    path.write_text(script, encoding='utf-8')
    return str(path)


# ── Gerenciador de banco externo ────────────────────────────────────────────────

class ExternalDBManager:
    """
    Gerencia a conexão ao banco externo opcional.
    Quando configurado, persiste:
    - Change log de todas as sessões
    - Dados importados de tabelas SAFX (opcional)
    - Configurações de conexão ERP
    """

    def __init__(self):
        self._conn = None
        self._db_type = 'sqlite'
        self._session_id = self._gen_session_id()

    @staticmethod
    def _gen_session_id() -> str:
        import uuid
        import datetime
        return f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"

    def connect(self, db_type: str, **kwargs) -> Tuple[bool, str]:
        """
        Conecta ao banco externo.
        kwargs varia por tipo:
          sqlite: path
          postgres/supabase: host, port, dbname, user, password  (ou dsn)
          oracle: host, port, user, password e um de: service_name, dbname, sid
          mysql: host, port, database, user, password
        """
        self._db_type = db_type
        try:
            if db_type == 'sqlite':
                import sqlite3
                path = kwargs.get('path', 'safx_data.db')
                self._conn = sqlite3.connect(path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._init_sqlite()

            elif db_type in ('postgres', 'supabase'):
                import psycopg2
                dsn = kwargs.get('dsn')
                if dsn:
                    self._conn = psycopg2.connect(dsn)
                else:
                    self._conn = psycopg2.connect(**{
                        k: kwargs[k] for k in ('host','port','dbname','user','password')
                        if k in kwargs})

            elif db_type == 'oracle':
                try:
                    import oracledb as _ora  # type: ignore
                except ImportError:
                    import cx_Oracle as _ora  # type: ignore
                # service_name (UI «Database»); aceita dbname por compat. com chamadas antigas
                svc = (kwargs.get('service_name') or kwargs.get('dbname') or '').strip()
                sid = (kwargs.get('sid') or '').strip()
                if not svc and not sid:
                    return False, (
                        "Oracle: informe o Service Name ou o SID no campo «Database» "
                        "(erro típico sem isso: ORA-12504 / listener recusou a conexão).")
                port = int(kwargs.get('port') or 1521)
                if sid and not svc:
                    dsn = _ora.makedsn(kwargs['host'], port, sid=sid)
                else:
                    dsn = _ora.makedsn(kwargs['host'], port, service_name=svc)
                if _ora.__name__ == 'cx_Oracle':
                    self._conn = _ora.connect(
                        kwargs['user'], kwargs['password'], dsn,
                        encoding='UTF-8')
                else:
                    self._conn = _ora.connect(
                        user=kwargs['user'],
                        password=kwargs['password'],
                        dsn=dsn,
                    )

            elif db_type == 'mysql':
                import pymysql
                self._conn = pymysql.connect(**{
                    k: kwargs[k] for k in ('host','port','database','user','password')
                    if k in kwargs})

            else:
                return False, f"Tipo '{db_type}' não suportado"

            return True, f"Conectado ao banco {db_type} com sucesso"

        except Exception as e:
            return False, str(e)

    def disconnect(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def is_connected(self) -> bool:
        return self._conn is not None

    def _init_sqlite(self):
        """Cria as tabelas no SQLite se não existirem."""
        self._conn.executescript(_SAFX_DDL_SQLITE)
        self._conn.commit()

    def persist_change_log(self, entries: List[Dict]) -> Tuple[int, str]:
        """Salva entradas do change log no banco externo."""
        if not self._conn or not entries:
            return 0, "não conectado ou sem entradas"
        try:
            cursor = self._conn.cursor()
            saved = 0
            for e in entries:
                if self._db_type == 'sqlite':
                    cursor.execute(
                        "INSERT INTO safx_change_log "
                        "(session_id,ts,table_name,row_id,field_name,"
                        "old_value,new_value,source,sql_snippet) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (self._session_id,
                         e.get('timestamp',''), e.get('table',''),
                         e.get('row_id',''), e.get('field',''),
                         e.get('old_value',''), e.get('new_value',''),
                         e.get('source',''), e.get('sql','')))
                else:
                    cursor.execute(
                        "INSERT INTO safx_change_log "
                        "(session_id,table_name,row_id,field_name,"
                        "old_value,new_value,source,sql_snippet) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (self._session_id,
                         e.get('table',''), e.get('row_id',''),
                         e.get('field',''), e.get('old_value',''),
                         e.get('new_value',''), e.get('source',''),
                         e.get('sql','')))
                saved += 1

            self._conn.commit()
            return saved, f"{saved} entradas salvas"
        except Exception as ex:
            return 0, str(ex)

    def save_table_data(self, table_name: str,
                        columns: List[str],
                        rows: List[tuple]) -> Tuple[int, str]:
        """
        Salva dados de uma tabela SAFX no banco externo.
        Cria a tabela dinamicamente se não existir.
        """
        if not self._conn:
            return 0, "não conectado"
        try:
            cursor = self._conn.cursor()
            safe = table_name.lower().replace(' ', '_')
            cols_noid = [c for c in columns if not c.startswith('_')]

            if self._db_type == 'sqlite':
                col_defs = ', '.join(f'"{c}" TEXT DEFAULT ""' for c in cols_noid)
                cursor.execute(f'DROP TABLE IF EXISTS "{safe}"')
                cursor.execute(
                    f'CREATE TABLE IF NOT EXISTS "{safe}" '
                    f'(_row_id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})')
                ph = ','.join('?' * len(cols_noid))
                col_idx = {c: i for i, c in enumerate(columns)}
                data = [
                    tuple(str(row[col_idx[c]]) if col_idx.get(c) is not None else ''
                          for c in cols_noid)
                    for row in rows
                ]
                cursor.executemany(
                    f'INSERT INTO "{safe}" ({",".join(cols_noid)}) VALUES ({ph})',
                    data)
            else:
                col_defs = ', '.join(f'"{c}" TEXT' for c in cols_noid)
                cursor.execute(f'DROP TABLE IF EXISTS {safe}')
                cursor.execute(
                    f'CREATE TABLE IF NOT EXISTS {safe} '
                    f'(_row_id BIGSERIAL PRIMARY KEY, {col_defs})')
                ph = ','.join('%s' * len(cols_noid))
                col_idx = {c: i for i, c in enumerate(columns)}
                data = [
                    tuple(str(row[col_idx[c]]) if col_idx.get(c) is not None else ''
                          for c in cols_noid)
                    for row in rows
                ]
                cursor.executemany(
                    f'INSERT INTO {safe} ({",".join(cols_noid)}) VALUES ({ph})',
                    data)

            self._conn.commit()
            return len(rows), f"{len(rows)} registros salvos em '{safe}'"
        except Exception as ex:
            return 0, str(ex)
