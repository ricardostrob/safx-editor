"""
Gerenciamento de configurações persistentes do SAFX Editor.
Salva/carrega configurações em JSON no diretório do usuário.
"""
import copy
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Diretório padrão: ~/.safx_editor/
CONFIG_DIR = Path.home() / ".safx_editor"
CONFIG_FILE = CONFIG_DIR / "config.json"

_EXT_DB_DEFAULTS: Dict[str, Any] = {
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
        "sftp_profile_id": "",
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
    "sftp_profiles": [],
    "sftp_active_profile_id": "",
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
    "ui": {
        "data_page_size": "Tudo",
    },
    "ext_db": dict(_EXT_DB_DEFAULTS),
    "ext_db_profiles": [],
    "ext_db_active_profile_id": "",
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

    def _ensure_connection_profiles(self):
        """Migra SFTP / banco externo único para listas de perfis (multi-cliente)."""
        d = self._data

        profs = d.get("sftp_profiles")
        if not isinstance(profs, list) or len(profs) == 0:
            old = dict(d.get("sftp") or DEFAULTS["sftp"])
            pid = str(uuid.uuid4())
            p: Dict[str, Any] = {"id": pid, "name": "Perfil 1"}
            for k, v in DEFAULTS["sftp"].items():
                p[k] = old.get(k, v)
            d["sftp_profiles"] = [p]
            d["sftp_active_profile_id"] = pid
        ids = {str(x.get("id")) for x in d["sftp_profiles"]
               if isinstance(x, dict) and x.get("id")}
        aid = str(d.get("sftp_active_profile_id") or "")
        if aid not in ids and d["sftp_profiles"]:
            d["sftp_active_profile_id"] = str(
                d["sftp_profiles"][0].get("id", ""))
        self._sync_flat_sftp_from_active()

        eprofs = d.get("ext_db_profiles")
        if not isinstance(eprofs, list) or len(eprofs) == 0:
            old_e = dict(d.get("ext_db") or DEFAULTS["ext_db"])
            eid = str(uuid.uuid4())
            ep: Dict[str, Any] = {"id": eid, "name": "Perfil 1"}
            for k, v in DEFAULTS["ext_db"].items():
                ep[k] = old_e.get(k, v)
            d["ext_db_profiles"] = [ep]
            d["ext_db_active_profile_id"] = eid
        eids = {str(x.get("id")) for x in d["ext_db_profiles"]
                if isinstance(x, dict) and x.get("id")}
        eaid = str(d.get("ext_db_active_profile_id") or "")
        if eaid not in eids and d["ext_db_profiles"]:
            d["ext_db_active_profile_id"] = str(
                d["ext_db_profiles"][0].get("id", ""))
        self._sync_flat_ext_db_from_active()

    def _merged_sftp_from_profiles(self) -> Dict[str, Any]:
        """Perfil SFTP ativo a partir de ``_data`` (sem ``ensure``/``sync`` — evita recursão)."""
        profs = self._data.get("sftp_profiles") or []
        aid = self._data.get("sftp_active_profile_id")
        sel: Optional[Dict[str, Any]] = None
        for p in profs:
            if isinstance(p, dict) and p.get("id") == aid:
                sel = p
                break
        if sel is None and profs:
            sel = profs[0]
        if not sel or not isinstance(sel, dict):
            return dict(DEFAULTS["sftp"])
        out = dict(DEFAULTS["sftp"])
        for k in DEFAULTS["sftp"]:
            out[k] = sel.get(k, out[k])
        return out

    def _merged_ext_db_from_profiles(self) -> Dict[str, Any]:
        """Perfil DB externo ativo a partir de ``_data`` (sem ``ensure``/``sync``)."""
        profs = self._data.get("ext_db_profiles") or []
        aid = self._data.get("ext_db_active_profile_id")
        sel: Optional[Dict[str, Any]] = None
        for p in profs:
            if isinstance(p, dict) and p.get("id") == aid:
                sel = p
                break
        if sel is None and profs:
            sel = profs[0]
        if not sel or not isinstance(sel, dict):
            return dict(DEFAULTS["ext_db"])
        out = dict(DEFAULTS["ext_db"])
        for k in DEFAULTS["ext_db"]:
            out[k] = sel.get(k, out[k])
        return out

    def _sync_flat_sftp_from_active(self):
        """Mantém a secção ``sftp`` plana = perfil ativo (compatibilidade / cripto)."""
        a = self._merged_sftp_from_profiles()
        base = dict(DEFAULTS["sftp"])
        for k in base:
            base[k] = a.get(k, base[k])
        self._data["sftp"] = base

    def _sync_flat_ext_db_from_active(self):
        a = self._merged_ext_db_from_profiles()
        base = dict(DEFAULTS["ext_db"])
        for k in base:
            base[k] = a.get(k, base[k])
        self._data["ext_db"] = base

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
        self._ensure_connection_profiles()

    def save(self):
        """Salva configurações no arquivo JSON."""
        self._save()

    _SENSITIVE_FIELDS = {
        'sftp':    ['password'],
        'api':     ['api_key'],
        'ext_db':  ['password'],
        'erp':     ['password', 'api_key'],
    }

    @staticmethod
    def _encrypt_password_in_profile_list(
            result: dict, list_key: str, pwd_field: str = 'password',
            encrypt_fn=None, is_enc_fn=None):
        lst = result.get(list_key)
        if not isinstance(lst, list) or not encrypt_fn:
            return
        for item in lst:
            if isinstance(item, dict):
                val = item.get(pwd_field, '')
                if val and not is_enc_fn(str(val)):
                    item[pwd_field] = encrypt_fn(str(val))

    @staticmethod
    def _decrypt_password_in_profile_list(
            result: dict, list_key: str, pwd_field: str = 'password',
            decrypt_fn=None, is_enc_fn=None):
        lst = result.get(list_key)
        if not isinstance(lst, list) or not decrypt_fn:
            return
        for item in lst:
            if isinstance(item, dict):
                val = item.get(pwd_field, '')
                if val and is_enc_fn(str(val)):
                    item[pwd_field] = decrypt_fn(str(val))

    def _encrypt_sensitive(self, data: dict) -> dict:
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
        self._encrypt_password_in_profile_list(
            result, 'sftp_profiles', 'password', encrypt, is_encrypted)
        self._encrypt_password_in_profile_list(
            result, 'ext_db_profiles', 'password', encrypt, is_encrypted)
        return result

    def _decrypt_sensitive(self, data: dict) -> dict:
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
        self._decrypt_password_in_profile_list(
            result, 'sftp_profiles', 'password', decrypt, is_encrypted)
        self._decrypt_password_in_profile_list(
            result, 'ext_db_profiles', 'password', decrypt, is_encrypted)
        return result

    def _save(self):
        self._sync_flat_sftp_from_active()
        self._sync_flat_ext_db_from_active()
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
        if section == "ext_db":
            return dict(self.get_active_ext_db_dict())
        return dict(self._data.get(section, DEFAULTS.get(section, {})))

    def set_section(self, section: str, values: Dict[str, Any]):
        if section not in self._data:
            self._data[section] = {}
        self._data[section].update(values)
        self._save()

    def get_value(self, section: str, key: str, default=None) -> Any:
        if section == "ext_db":
            return self.get_active_ext_db_dict().get(key, default)
        return self._data.get(section, {}).get(key, default)

    def set_value(self, section: str, key: str, value: Any):
        if section == "ext_db":
            self._ensure_connection_profiles()
            aid = self._data.get("ext_db_active_profile_id")
            for p in self._data.get("ext_db_profiles") or []:
                if isinstance(p, dict) and p.get("id") == aid:
                    p[key] = value
                    break
            self._sync_flat_ext_db_from_active()
            self._save()
            return
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
        self._save()

    def reset_section(self, section: str):
        self._data[section] = dict(DEFAULTS.get(section, {}))
        self._save()

    def reset_all(self):
        self._data = self._deep_merge({}, DEFAULTS)
        self._ensure_connection_profiles()
        self._save()

    # ─── SFTP: vários perfis ─────────────────────────────────────────────────

    def list_sftp_profiles(self) -> List[Dict[str, Any]]:
        self._ensure_connection_profiles()
        return copy.deepcopy(self._data.get("sftp_profiles") or [])

    def set_sftp_profiles_state(
            self, profiles: List[Dict[str, Any]], active_profile_id: str):
        self._data["sftp_profiles"] = copy.deepcopy(profiles)
        self._data["sftp_active_profile_id"] = active_profile_id or (
            profiles[0].get("id", "") if profiles else "")
        self._sync_flat_sftp_from_active()
        self._save()

    def get_sftp_active_profile_id(self) -> str:
        self._ensure_connection_profiles()
        return str(self._data.get("sftp_active_profile_id") or "")

    def get_active_sftp_dict(self) -> Dict[str, Any]:
        """Campos de conexão do perfil SFTP ativo (SFTPManager / testes)."""
        self._ensure_connection_profiles()
        return self._merged_sftp_from_profiles()

    def get_sftp_profile_for_export(self) -> Dict[str, Any]:
        """Perfil usado na exportação quando ``export.sftp_profile_id`` está vazio → ativo."""
        self._ensure_connection_profiles()
        eid = self.get_value("export", "sftp_profile_id", "") or ""
        if not eid:
            return self.get_active_sftp_dict()
        for p in self._data.get("sftp_profiles") or []:
            if isinstance(p, dict) and str(p.get("id")) == str(eid):
                out = dict(DEFAULTS["sftp"])
                for k in DEFAULTS["sftp"]:
                    out[k] = p.get(k, out[k])
                return out
        return self.get_active_sftp_dict()

    @property
    def sftp(self) -> Dict[str, Any]:
        return self.get_active_sftp_dict()

    # ─── Banco externo: vários perfis ───────────────────────────────────────

    def list_ext_db_profiles(self) -> List[Dict[str, Any]]:
        self._ensure_connection_profiles()
        return copy.deepcopy(self._data.get("ext_db_profiles") or [])

    def set_ext_db_profiles_state(
            self, profiles: List[Dict[str, Any]], active_profile_id: str):
        self._data["ext_db_profiles"] = copy.deepcopy(profiles)
        self._data["ext_db_active_profile_id"] = active_profile_id or (
            profiles[0].get("id", "") if profiles else "")
        self._sync_flat_ext_db_from_active()
        self._save()

    def get_ext_db_active_profile_id(self) -> str:
        self._ensure_connection_profiles()
        return str(self._data.get("ext_db_active_profile_id") or "")

    def get_active_ext_db_dict(self) -> Dict[str, Any]:
        self._ensure_connection_profiles()
        return self._merged_ext_db_from_profiles()

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
