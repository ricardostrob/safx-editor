"""
Módulo de segurança do SAFX Editor.
Criptografia de senhas e dados sensíveis, geração de chave vinculada à máquina.

Desenvolvido por: Lucas Ricardo Strob Mancegozo Lima ME
Empresa: Adejo Tecnologia / TecTex
PROIBIDA A VENDA SEM AUTORIZAÇÃO DOS DESENVOLVEDORES.
"""
import os
import sys
import base64
import hashlib
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_KEY_FILE = Path.home() / ".safx_editor" / ".keystore"


def _get_machine_fingerprint() -> str:
    """
    Gera uma impressão digital da máquina combinando informações de hardware.
    A chave de criptografia é derivada desta impressão — o config é amarrado à máquina.
    """
    parts = []

    # Nome do host
    parts.append(platform.node() or 'unknown-host')

    # Sistema operacional
    parts.append(platform.system() + platform.release())

    # ID de máquina (Linux/Mac /etc/machine-id, Windows registry)
    try:
        if sys.platform == 'win32':
            result = subprocess.check_output(
                ['wmic', 'csproduct', 'get', 'UUID'],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode(errors='ignore')
            uuid_line = [l.strip() for l in result.splitlines() if l.strip() and 'UUID' not in l]
            if uuid_line:
                parts.append(uuid_line[0])
        elif sys.platform == 'darwin':
            result = subprocess.check_output(
                ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode(errors='ignore')
            for line in result.splitlines():
                if 'IOPlatformUUID' in line:
                    parts.append(line.split('"')[-2])
                    break
        else:
            mid = Path('/etc/machine-id')
            if mid.exists():
                parts.append(mid.read_text().strip())
    except Exception:
        pass

    # Usuário atual
    parts.append(os.environ.get('USERNAME') or os.environ.get('USER') or 'user')

    combined = '|'.join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def _derive_key(fingerprint: str, salt: bytes) -> bytes:
    """Deriva uma chave Fernet de 32 bytes a partir da impressão da máquina."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=300_000,
    )
    key_bytes = kdf.derive(fingerprint.encode())
    return base64.urlsafe_b64encode(key_bytes)


def _load_or_create_key() -> bytes:
    """Carrega ou cria a chave de criptografia local."""
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)

    if _KEY_FILE.exists():
        try:
            data = _KEY_FILE.read_bytes()
            if len(data) >= 32:
                salt = data[:16]
                fp = _get_machine_fingerprint()
                return _derive_key(fp, salt)
        except Exception:
            pass

    # Cria nova chave
    salt = os.urandom(16)
    fp = _get_machine_fingerprint()
    key = _derive_key(fp, salt)
    _KEY_FILE.write_bytes(salt + b'SAFX_KEYSTORE_V1')
    # Restringe permissões em sistemas Unix
    try:
        _KEY_FILE.chmod(0o600)
    except Exception:
        pass
    return key


def encrypt(value: str) -> str:
    """Criptografa um texto e retorna string base64 segura para armazenar."""
    if not value:
        return ''
    try:
        from cryptography.fernet import Fernet
        key = _load_or_create_key()
        f = Fernet(key)
        return f.encrypt(value.encode('utf-8')).decode('ascii')
    except Exception as e:
        logger.warning(f"Encrypt failed: {e}")
        return value   # Fallback sem criptografia


def decrypt(value: str) -> str:
    """Descriptografa um valor previamente criptografado."""
    if not value:
        return ''
    try:
        from cryptography.fernet import Fernet, InvalidToken
        key = _load_or_create_key()
        f = Fernet(key)
        return f.decrypt(value.encode('ascii')).decode('utf-8')
    except Exception:
        # Pode ser valor em texto plano (retrocompatibilidade)
        return value


def is_encrypted(value: str) -> bool:
    """Verifica se o valor parece ser texto criptografado (token Fernet)."""
    if not value:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value + '==')
        return decoded[:1] == b'\x80'   # Versão Fernet
    except Exception:
        return False


# ── Verificação de integridade ────────────────────────────────────────────────

def compute_file_hash(path: str) -> str:
    """Calcula hash SHA-256 de um arquivo."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def generate_integrity_manifest(base_dir: str) -> dict:
    """Gera manifesto de integridade de todos os arquivos .py do projeto."""
    manifest = {}
    base = Path(base_dir)
    for pyfile in sorted(base.rglob('*.py')):
        rel = str(pyfile.relative_to(base))
        manifest[rel] = compute_file_hash(str(pyfile))
    return manifest


def verify_integrity(base_dir: str, manifest: dict) -> Tuple[bool, list]:
    """Verifica integridade dos arquivos contra o manifesto."""
    base = Path(base_dir)
    violations = []
    for rel_path, expected_hash in manifest.items():
        full = base / rel_path
        if not full.exists():
            violations.append(f"AUSENTE: {rel_path}")
            continue
        actual = compute_file_hash(str(full))
        if actual != expected_hash:
            violations.append(f"MODIFICADO: {rel_path}")
    return len(violations) == 0, violations


# ── Rate limiting básico para API ─────────────────────────────────────────────

import time
import threading

class RateLimiter:
    """Rate limiter simples por IP para a API REST."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._counts: dict = {}
        self._lock = threading.Lock()

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            if ip not in self._counts:
                self._counts[ip] = []
            # Remove eventos fora da janela
            self._counts[ip] = [t for t in self._counts[ip] if now - t < self._window]
            if len(self._counts[ip]) >= self._max:
                return False
            self._counts[ip].append(now)
            return True

    def cleanup(self):
        now = time.time()
        with self._lock:
            for ip in list(self._counts.keys()):
                self._counts[ip] = [t for t in self._counts[ip] if now - t < self._window]
                if not self._counts[ip]:
                    del self._counts[ip]


# Instância global do rate limiter
_api_rate_limiter = RateLimiter(max_requests=120, window_seconds=60)


def check_api_rate_limit(ip: str) -> bool:
    return _api_rate_limiter.is_allowed(ip)
