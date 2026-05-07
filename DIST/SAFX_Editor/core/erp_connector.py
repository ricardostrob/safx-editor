"""
Conectores para importação direta de dados SAFX de sistemas ERP
(Oracle DB, SAP via RFC/REST, TOTVS Fluig/Protheus, PostgreSQL, MySQL, Supabase).

Cada conector retorna os dados no mesmo formato que o parser de TXT:
    List[Dict[str, str]]  — lista de dicionários campo → valor
"""
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ERPConnectionConfig:
    """Configuração genérica de uma conexão ERP/DB."""
    type: str = 'oracle'       # oracle | sap_rfc | sap_rest | totvs_rest | postgres | mysql | supabase | odbc
    host: str = ''
    port: int = 0
    database: str = ''         # service_name (Oracle), database (PG/MySQL), base (TOTVS)
    username: str = ''
    password: str = ''
    # SAP específico
    sap_client: str = '100'
    sap_sysnr: str = '00'
    sap_lang: str = 'PT'
    # REST / Supabase
    api_url: str = ''
    api_key: str = ''
    # ODBC
    dsn: str = ''
    # Mapeamento de tabelas
    table_mappings: Dict[str, str] = field(default_factory=dict)
    # SQL/query personalizada por tabela SAFX
    custom_queries: Dict[str, str] = field(default_factory=dict)
    # Encoding padrão
    encoding: str = 'utf-8'
    # Nome para exibição
    display_name: str = ''

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ERPConnectionConfig':
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


class ERPConnectorError(Exception):
    pass


def _test_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


class OracleConnector:
    """Conecta ao Oracle DB via cx_Oracle."""

    DRIVER = 'cx_Oracle'
    DISPLAY = 'Oracle Database'

    def __init__(self, cfg: ERPConnectionConfig):
        self.cfg = cfg

    @classmethod
    def is_available(cls) -> bool:
        return _test_import(cls.DRIVER)

    def connect(self):
        import cx_Oracle  # noqa
        dsn = cx_Oracle.makedsn(
            self.cfg.host,
            self.cfg.port or 1521,
            service_name=self.cfg.database or self.cfg.dsn
        )
        return cx_Oracle.connect(
            user=self.cfg.username,
            password=self.cfg.password,
            dsn=dsn,
            encoding=self.cfg.encoding
        )

    def fetch_safx_table(self, table_name: str,
                         where_clause: str = '',
                         progress_cb=None) -> Tuple[List[str], List[Dict]]:
        """
        Busca dados de uma tabela SAFX no Oracle.
        Usa query customizada se configurada, senão SELECT * FROM <mapping>.
        """
        conn = self.connect()
        try:
            cursor = conn.cursor()
            sql = self.cfg.custom_queries.get(table_name)
            if not sql:
                source = self.cfg.table_mappings.get(table_name, table_name)
                sql = f'SELECT * FROM {source}'
                if where_clause:
                    sql += f' WHERE {where_clause}'

            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = []
            batch = cursor.fetchmany(5000)
            total = 0
            while batch:
                for row in batch:
                    rows.append({
                        columns[i]: str(v) if v is not None else ''
                        for i, v in enumerate(row)
                    })
                total += len(batch)
                if progress_cb:
                    progress_cb(total)
                batch = cursor.fetchmany(5000)
            return columns, rows
        finally:
            conn.close()


class PostgreSQLConnector:
    """Conecta via psycopg2 — suporta PostgreSQL e Supabase (via connection string)."""

    DRIVER = 'psycopg2'
    DISPLAY = 'PostgreSQL / Supabase'

    def __init__(self, cfg: ERPConnectionConfig):
        self.cfg = cfg

    @classmethod
    def is_available(cls) -> bool:
        return _test_import(cls.DRIVER)

    def connect(self):
        import psycopg2  # noqa
        if self.cfg.api_url and 'supabase' in self.cfg.api_url.lower():
            # Supabase connection string
            return psycopg2.connect(self.cfg.api_url)
        return psycopg2.connect(
            host=self.cfg.host,
            port=self.cfg.port or 5432,
            dbname=self.cfg.database,
            user=self.cfg.username,
            password=self.cfg.password
        )

    def fetch_safx_table(self, table_name: str,
                         where_clause: str = '',
                         progress_cb=None) -> Tuple[List[str], List[Dict]]:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            sql = self.cfg.custom_queries.get(table_name)
            if not sql:
                source = self.cfg.table_mappings.get(table_name, table_name.lower())
                sql = f'SELECT * FROM {source}'
                if where_clause:
                    sql += f' WHERE {where_clause}'

            cursor.execute(sql)
            columns = [desc[0].upper() for desc in cursor.description]
            rows = []
            for row in cursor:
                rows.append({
                    columns[i]: str(v) if v is not None else ''
                    for i, v in enumerate(row)
                })
            return columns, rows
        finally:
            conn.close()


class MySQLConnector:
    """Conecta via pymysql."""

    DRIVER = 'pymysql'
    DISPLAY = 'MySQL / MariaDB'

    def __init__(self, cfg: ERPConnectionConfig):
        self.cfg = cfg

    @classmethod
    def is_available(cls) -> bool:
        return _test_import(cls.DRIVER)

    def connect(self):
        import pymysql  # noqa
        return pymysql.connect(
            host=self.cfg.host,
            port=self.cfg.port or 3306,
            db=self.cfg.database,
            user=self.cfg.username,
            password=self.cfg.password,
            charset='utf8mb4'
        )

    def fetch_safx_table(self, table_name: str,
                         where_clause: str = '',
                         progress_cb=None) -> Tuple[List[str], List[Dict]]:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            sql = self.cfg.custom_queries.get(table_name)
            if not sql:
                source = self.cfg.table_mappings.get(table_name, table_name.lower())
                sql = f'SELECT * FROM `{source}`'
                if where_clause:
                    sql += f' WHERE {where_clause}'

            cursor.execute(sql)
            columns = [desc[0].upper() for desc in cursor.description]
            rows = []
            for row in cursor:
                rows.append({
                    columns[i]: str(v) if v is not None else ''
                    for i, v in enumerate(row)
                })
            return columns, rows
        finally:
            conn.close()


class SupabaseRESTConnector:
    """
    Conecta ao Supabase via API REST (sem driver de banco de dados).
    Usa a supabase-py client ou requests puro.
    """

    DRIVER = 'requests'
    DISPLAY = 'Supabase (REST API)'

    def __init__(self, cfg: ERPConnectionConfig):
        self.cfg = cfg

    @classmethod
    def is_available(cls) -> bool:
        return _test_import('requests')

    def fetch_safx_table(self, table_name: str,
                         where_clause: str = '',
                         progress_cb=None) -> Tuple[List[str], List[Dict]]:
        import requests  # noqa
        source = self.cfg.table_mappings.get(table_name, table_name.lower())
        url = f"{self.cfg.api_url.rstrip('/')}/rest/v1/{source}"
        headers = {
            'apikey': self.cfg.api_key,
            'Authorization': f'Bearer {self.cfg.api_key}',
            'Prefer': 'count=exact',
        }
        params = {'select': '*', 'limit': 1000, 'offset': 0}

        all_rows = []
        while True:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            if not all_rows:
                columns = list(data[0].keys()) if data else []
            all_rows.extend(data)
            if progress_cb:
                progress_cb(len(all_rows))
            params['offset'] += len(data)
            if len(data) < params['limit']:
                break

        columns_upper = [c.upper() for c in (columns if all_rows else [])]
        rows = [
            {columns_upper[i]: str(v) if v is not None else ''
             for i, v in enumerate(row.values())}
            for row in all_rows
        ]
        return columns_upper, rows


class TOTVSConnector:
    """Conecta ao TOTVS Protheus/Fluig via REST API."""

    DRIVER = 'requests'
    DISPLAY = 'TOTVS Protheus / Fluig (REST)'

    def __init__(self, cfg: ERPConnectionConfig):
        self.cfg = cfg

    @classmethod
    def is_available(cls) -> bool:
        return _test_import('requests')

    def fetch_safx_table(self, table_name: str,
                         where_clause: str = '',
                         progress_cb=None) -> Tuple[List[str], List[Dict]]:
        """
        Busca via REST Protheus. O endpoint deve ser configurado em
        custom_queries[table_name] como URL ou em table_mappings[table_name]
        como nome da entidade.
        """
        import requests  # noqa
        import base64

        endpoint = self.cfg.custom_queries.get(
            table_name,
            f"{self.cfg.api_url.rstrip('/')}/{self.cfg.table_mappings.get(table_name, table_name)}"
        )

        creds = base64.b64encode(
            f"{self.cfg.username}:{self.cfg.password}".encode()).decode()
        headers = {
            'Authorization': f'Basic {creds}',
            'Content-Type': 'application/json',
        }

        all_rows = []
        page = 1
        columns = []

        while True:
            params = {'page': page, 'pageSize': 500}
            if self.cfg.database:
                params['company'] = self.cfg.database

            resp = requests.get(endpoint, headers=headers,
                                params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            items = data.get('items', data if isinstance(data, list) else [])
            if not items:
                break

            if not columns and items:
                columns = [k.upper() for k in items[0].keys()]

            for item in items:
                all_rows.append({
                    k.upper(): str(v) if v is not None else ''
                    for k, v in item.items()
                })

            if progress_cb:
                progress_cb(len(all_rows))

            total = data.get('total', len(all_rows))
            if len(all_rows) >= total:
                break
            page += 1

        return columns, all_rows


class SAPRFCConnector:
    """
    Conecta ao SAP via pyrfc (SAP NetWeaver RFC SDK).
    Requer instalação do pyrfc e do SAP NW RFC Library.
    """

    DRIVER = 'pyrfc'
    DISPLAY = 'SAP (RFC / BAPI)'

    def __init__(self, cfg: ERPConnectionConfig):
        self.cfg = cfg

    @classmethod
    def is_available(cls) -> bool:
        return _test_import(cls.DRIVER)

    def connect(self):
        import pyrfc  # noqa
        return pyrfc.Connection(
            ashost=self.cfg.host,
            sysnr=self.cfg.sap_sysnr,
            client=self.cfg.sap_client,
            user=self.cfg.username,
            passwd=self.cfg.password,
            lang=self.cfg.sap_lang
        )

    def fetch_safx_table(self, table_name: str,
                         where_clause: str = '',
                         progress_cb=None) -> Tuple[List[str], List[Dict]]:
        """
        Usa RFC_READ_TABLE para buscar dados diretamente de tabelas SAP.
        O table_name deve ser mapeado para o nome da tabela SAP em table_mappings.
        """
        conn = self.connect()
        try:
            sap_table = self.cfg.table_mappings.get(table_name, table_name)
            params: Dict[str, Any] = {
                'QUERY_TABLE': sap_table,
                'DELIMITER': '|',
                'ROWCOUNT': 0,
            }
            if where_clause:
                params['OPTIONS'] = [{'TEXT': where_clause}]

            result = conn.call('RFC_READ_TABLE', **params)

            fields = [f['FIELDNAME'] for f in result['FIELDS']]
            rows = []
            for line in result['DATA']:
                values = line['WA'].split('|')
                rows.append({fields[i]: v.strip()
                             for i, v in enumerate(values) if i < len(fields)})
                if progress_cb and len(rows) % 5000 == 0:
                    progress_cb(len(rows))

            return fields, rows
        finally:
            conn.close()


class ODBCConnector:
    """Conecta via pyodbc — suporte genérico a qualquer fonte ODBC."""

    DRIVER = 'pyodbc'
    DISPLAY = 'ODBC (genérico)'

    def __init__(self, cfg: ERPConnectionConfig):
        self.cfg = cfg

    @classmethod
    def is_available(cls) -> bool:
        return _test_import(cls.DRIVER)

    def connect(self):
        import pyodbc  # noqa
        if self.cfg.dsn:
            return pyodbc.connect(f'DSN={self.cfg.dsn};'
                                  f'UID={self.cfg.username};PWD={self.cfg.password}')
        return pyodbc.connect(self.cfg.api_url)  # connection string completa

    def fetch_safx_table(self, table_name: str,
                         where_clause: str = '',
                         progress_cb=None) -> Tuple[List[str], List[Dict]]:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            sql = self.cfg.custom_queries.get(table_name)
            if not sql:
                source = self.cfg.table_mappings.get(table_name, table_name)
                sql = f'SELECT * FROM {source}'
                if where_clause:
                    sql += f' WHERE {where_clause}'
            cursor.execute(sql)
            columns = [desc[0].upper() for desc in cursor.description]
            rows = []
            for row in cursor:
                rows.append({columns[i]: str(v) if v is not None else ''
                             for i, v in enumerate(row)})
                if progress_cb and len(rows) % 5000 == 0:
                    progress_cb(len(rows))
            return columns, rows
        finally:
            conn.close()


# Registro central de conectores
CONNECTORS = {
    'oracle':      OracleConnector,
    'postgres':    PostgreSQLConnector,
    'supabase':    PostgreSQLConnector,
    'supabase_rest': SupabaseRESTConnector,
    'mysql':       MySQLConnector,
    'totvs_rest':  TOTVSConnector,
    'sap_rfc':     SAPRFCConnector,
    'odbc':        ODBCConnector,
}

CONNECTOR_LABELS = {
    'oracle':        'Oracle Database (cx_Oracle)',
    'postgres':      'PostgreSQL (psycopg2)',
    'supabase':      'Supabase (PostgreSQL)',
    'supabase_rest': 'Supabase (REST API)',
    'mysql':         'MySQL / MariaDB (pymysql)',
    'totvs_rest':    'TOTVS Protheus / Fluig (REST)',
    'sap_rfc':       'SAP (RFC via pyrfc)',
    'odbc':          'ODBC Genérico (pyodbc)',
}

CONNECTOR_PORTS = {
    'oracle': 1521, 'postgres': 5432, 'supabase': 5432,
    'mysql': 3306, 'totvs_rest': 8080, 'sap_rfc': 0,
    'supabase_rest': 443, 'odbc': 0,
}


def get_connector(cfg: ERPConnectionConfig):
    """Instancia o conector correto para o tipo configurado."""
    cls = CONNECTORS.get(cfg.type)
    if not cls:
        raise ERPConnectorError(f"Tipo de conector desconhecido: {cfg.type}")
    return cls(cfg)


def check_dependencies() -> Dict[str, bool]:
    """Verifica quais drivers estão disponíveis."""
    return {
        'oracle':        _test_import('cx_Oracle'),
        'postgres':      _test_import('psycopg2'),
        'supabase_rest': _test_import('requests'),
        'mysql':         _test_import('pymysql'),
        'totvs_rest':    _test_import('requests'),
        'sap_rfc':       _test_import('pyrfc'),
        'odbc':          _test_import('pyodbc'),
    }
