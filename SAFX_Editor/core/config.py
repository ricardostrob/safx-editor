"""
Gerenciamento de configurações persistentes do SAFX Editor.
Salva/carrega configurações em JSON no diretório do usuário.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Diretório padrão: ~/.safx_editor/
CONFIG_DIR = Path.home() / ".safx_editor"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: Dict[str, Any] = {
    "general": {
        "theme": "dark",
        "accent_color": "#89b4fa",
        "font_size": 12,
        "language": "pt_BR",
        "page_size": 500,
        "auto_limit_select": True,
        "select_limit": 10000,
        "show_row_numbers": True,
        "confirm_on_rollback": True,
        "layout_dir": "",
    },
    "export": {
        "default_destination": "local",   # local | sftp | dir
        "local_dir": str(Path.home() / "Downloads"),
        "server_dir": "",
        "encoding": "latin-1",
        "line_ending": "CRLF",
        "open_after_export": False,
    },
    "sftp": {
        "enabled": False,
        "host": "",
        "port": 22,
        "username": "",
        "password": "",
        "key_path": "",
        "remote_path": "/",
        "timeout": 30,
        "passive_mode": True,
    },
    # Lista de perfis SFTP (suporte a múltiplos sistemas/clientes)
    "sftp_profiles": [],
    # Lista de perfis de banco externo
    "db_profiles": [],
    "api": {
        "enabled": False,
        "host": "0.0.0.0",
        "port": 8787,
        "api_key": "",
        "cors_origins": "*",
        "read_only": False,
        "log_requests": True,
    },
    "branding": {
        "company_name": "Adejo Desenvolvimento",
        "primary_color": "#0e1b2e",
        "accent_color": "#89b4fa",
        "logo_path": "",
        "show_logo": True,
    },
    "window": {
        "width": 1400,
        "height": 850,
        "maximized": False,
        "splitter_data_sql": [600, 300],
    },
}


class AppConfig:
    """Configuração persistente do SAFX Editor."""

    _instance: Optional["AppConfig"] = None

    @classmethod
    def get(cls) -> "AppConfig":
        if cls._instance is None:
            cls._instance = AppConfig()
        return cls._instance

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        """Carrega configurações do arquivo JSON."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding='utf-8') as f:
                    saved = json.load(f)
                saved = self._decrypt_sensitive(saved)
                self._data = self._deep_merge(DEFAULTS, saved)
            except Exception as e:
                logger.warning(f"Erro ao carregar config: {e} — usando padrões")
                self._data = self._deep_merge({}, DEFAULTS)
        else:
            self._data = self._deep_merge({}, DEFAULTS)
            self._save()

    def save(self):
        """Salva configurações no arquivo JSON."""
        self._save()

    # Campos de senha/chave que devem ser criptografados antes de salvar
    _SENSITIVE_FIELDS = {
        'sftp':    ['password'],
        'api':     ['api_key'],
        'ext_db':  ['password'],
        'erp':     ['password', 'api_key'],
    }

    def _encrypt_sensitive(self, data: dict) -> dict:
        """Criptografa campos sensíveis antes de salvar."""
        try:
            from core.security import encrypt, is_encrypted
        except ImportError:
            return data
        result = {k: dict(v) if isinstance(v, dict) else v for k, v in data.items()}
        for section, fields in self._SENSITIVE_FIELDS.items():
            if section in result and isinstance(result[section], dict):
                for field in fields:
                    val = result[section].get(field, '')
                    if val and not is_encrypted(str(val)):
                        result[section][field] = encrypt(str(val))
        return result

    def _decrypt_sensitive(self, data: dict) -> dict:
        """Descriptografa campos sensíveis ao carregar."""
        try:
            from core.security import decrypt, is_encrypted
        except ImportError:
            return data
        result = {k: dict(v) if isinstance(v, dict) else v for k, v in data.items()}
        for section, fields in self._SENSITIVE_FIELDS.items():
            if section in result and isinstance(result[section], dict):
                for field in fields:
                    val = result[section].get(field, '')
                    if val and is_encrypted(str(val)):
                        result[section][field] = decrypt(str(val))
        return result

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            safe_data = self._encrypt_sensitive(self._data)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(safe_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar config: {e}")

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def get_section(self, section: str) -> Dict[str, Any]:
        return dict(self._data.get(section, DEFAULTS.get(section, {})))

    def set_section(self, section: str, values: Dict[str, Any]):
        if section not in self._data:
            self._data[section] = {}
        self._data[section].update(values)
        self._save()

    def get_value(self, section: str, key: str, default=None) -> Any:
        return self._data.get(section, {}).get(key, default)

    def set_value(self, section: str, key: str, value: Any):
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
        self._save()

    def reset_section(self, section: str):
        self._data[section] = dict(DEFAULTS.get(section, {}))
        self._save()

    def reset_all(self):
        self._data = self._deep_merge({}, DEFAULTS)
        self._save()

    # ─── Atalhos comuns ───────────────────────────────────────────────────────

    # ─── Perfis SFTP (múltiplos) ──────────────────────────────────────────────

    _DEFAULT_SFTP_PROFILE: Dict[str, Any] = {
        "name": "Principal",
        "enabled": True,
        "host": "",
        "port": 22,
        "username": "",
        "password": "",
        "key_path": "",
        "remote_path": "/",
        "timeout": 30,
    }

    def get_sftp_profiles(self) -> list:
        """Retorna lista de perfis SFTP. Migra configuração antiga se necessário."""
        profiles = list(self._data.get('sftp_profiles', []))
        if not profiles:
            old = self._data.get('sftp', {})
            if old.get('host'):
                migrated = dict(self._DEFAULT_SFTP_PROFILE)
                migrated.update({k: old[k] for k in self._DEFAULT_SFTP_PROFILE if k in old})
                migrated['name'] = old.get('host', 'Principal')
                profiles = [migrated]
        return profiles

    def save_sftp_profiles(self, profiles: list):
        self._data['sftp_profiles'] = profiles
        # Mantém seção 'sftp' sincronizada com o primeiro perfil (retrocompatibilidade)
        if profiles:
            self._data['sftp'] = dict(profiles[0])
        self._save()

    # ─── Perfis Banco Externo (múltiplos) ─────────────────────────────────────

    _DEFAULT_DB_PROFILE: Dict[str, Any] = {
        "name": "Banco Principal",
        "enabled": False,
        "type": "sqlite",
        "host": "",
        "port": 5432,
        "database": "",
        "username": "",
        "password": "",
        "persist_tables": False,
        "persist_log": True,
    }

    def get_db_profiles(self) -> list:
        """Retorna lista de perfis de banco externo. Migra config antiga."""
        profiles = list(self._data.get('db_profiles', []))
        if not profiles:
            old = self._data.get('ext_db', {})
            if old.get('host') or old.get('type'):
                migrated = dict(self._DEFAULT_DB_PROFILE)
                migrated.update({k: old[k] for k in self._DEFAULT_DB_PROFILE if k in old})
                profiles = [migrated]
        return profiles

    def save_db_profiles(self, profiles: list):
        self._data['db_profiles'] = profiles
        if profiles:
            self._data['ext_db'] = dict(profiles[0])
        self._save()

    @property
    def sftp(self) -> Dict[str, Any]:
        profiles = self.get_sftp_profiles()
        return profiles[0] if profiles else self.get_section("sftp")

    @property
    def api(self) -> Dict[str, Any]:
        return self.get_section("api")

    @property
    def export(self) -> Dict[str, Any]:
        return self.get_section("export")

    @property
    def general(self) -> Dict[str, Any]:
        return self.get_section("general")

    @property
    def branding(self) -> Dict[str, Any]:
        return self.get_section("branding")

    @property
    def window(self) -> Dict[str, Any]:
        return self.get_section("window")
