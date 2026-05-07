"""
Gerenciador SFTP para envio de arquivos exportados.
Usa paramiko para conexão SSH/SFTP.
"""
import logging
import os
from pathlib import Path
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)


def _paramiko_available() -> bool:
    try:
        import paramiko  # noqa: F401
        return True
    except ImportError:
        return False


class SFTPManager:
    """Realiza upload de arquivos via SFTP usando paramiko."""

    def __init__(self, host: str, port: int = 22, username: str = "",
                 password: str = "", key_path: str = "",
                 remote_path: str = "/", timeout: int = 30):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.remote_path = remote_path
        self.timeout = timeout
        self._client = None
        self._sftp = None

    def connect(self) -> Tuple[bool, str]:
        """Estabelece conexão SFTP. Retorna (sucesso, mensagem)."""
        if not _paramiko_available():
            return False, ("Biblioteca 'paramiko' nao instalada.\n"
                           "Execute: pip install paramiko")

        import paramiko

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": self.timeout,
                "look_for_keys": False,
                "allow_agent": False,
            }

            if self.key_path and os.path.exists(self.key_path):
                connect_kwargs["key_filename"] = self.key_path
                if self.password:
                    connect_kwargs["passphrase"] = self.password
            elif self.password:
                connect_kwargs["password"] = self.password
            else:
                return False, "Informe senha ou caminho de chave SSH"

            client.connect(**connect_kwargs)
            self._client = client
            self._sftp = client.open_sftp()
            logger.info(f"SFTP conectado em {self.host}:{self.port}")
            return True, f"Conectado ao SFTP {self.host}:{self.port}"

        except Exception as e:
            logger.error(f"Erro SFTP: {e}")
            return False, f"Erro de conexao SFTP: {e}"

    def disconnect(self):
        """Fecha conexão SFTP."""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._sftp = None
        self._client = None

    def upload_file(self, local_path: str,
                    remote_filename: Optional[str] = None,
                    progress_callback: Optional[Callable] = None
                    ) -> Tuple[bool, str]:
        """
        Envia arquivo local para o servidor SFTP.
        Retorna (sucesso, mensagem).
        """
        if not self._sftp:
            ok, msg = self.connect()
            if not ok:
                return False, msg

        local = Path(local_path)
        if not local.exists():
            return False, f"Arquivo nao encontrado: {local_path}"

        remote_file = remote_filename or local.name
        remote_full = self.remote_path.rstrip('/') + '/' + remote_file

        try:
            # Garante que o diretório remoto existe
            self._ensure_remote_dir(self.remote_path)

            file_size = local.stat().st_size

            def _progress(transferred: int, total: int):
                if progress_callback:
                    progress_callback(transferred, total)

            self._sftp.put(str(local), remote_full, callback=_progress)
            logger.info(f"Upload SFTP: {local.name} -> {remote_full}")
            return True, (f"Arquivo enviado com sucesso!\n"
                          f"Destino: {self.host}:{remote_full}\n"
                          f"Tamanho: {file_size / 1024:.1f} KB")

        except Exception as e:
            logger.error(f"Erro no upload SFTP: {e}")
            return False, f"Erro no upload: {e}"

    def _ensure_remote_dir(self, remote_dir: str):
        """Cria diretório remoto recursivamente se não existir."""
        if not self._sftp:
            return
        parts = remote_dir.strip('/').split('/')
        current = ''
        for part in parts:
            if not part:
                continue
            current += '/' + part
            try:
                self._sftp.stat(current)
            except IOError:
                try:
                    self._sftp.mkdir(current)
                except Exception:
                    pass

    def list_remote(self, path: Optional[str] = None) -> Tuple[bool, list]:
        """Lista arquivos no diretório remoto."""
        if not self._sftp:
            ok, msg = self.connect()
            if not ok:
                return False, [msg]

        try:
            target = path or self.remote_path
            files = self._sftp.listdir_attr(target)
            result = []
            for f in files:
                import stat
                is_dir = stat.S_ISDIR(f.st_mode)
                result.append({
                    "name": f.filename,
                    "size": f.st_size,
                    "is_dir": is_dir,
                    "modified": f.st_mtime,
                })
            return True, result
        except Exception as e:
            return False, [str(e)]

    def test_connection(self) -> Tuple[bool, str]:
        """Testa a conexão SFTP e retorna status."""
        ok, msg = self.connect()
        if ok:
            try:
                items = self._sftp.listdir(self.remote_path)
                msg += f"\nDiretorio remoto contém {len(items)} item(s)"
            except Exception as e:
                msg += f"\nAviso: nao foi possivel listar '{self.remote_path}': {e}"
            finally:
                self.disconnect()
        return ok, msg

    @classmethod
    def from_config(cls, cfg: dict) -> "SFTPManager":
        """Cria instância a partir de configuração."""
        return cls(
            host=cfg.get("host", ""),
            port=cfg.get("port", 22),
            username=cfg.get("username", ""),
            password=cfg.get("password", ""),
            key_path=cfg.get("key_path", ""),
            remote_path=cfg.get("remote_path", "/"),
            timeout=cfg.get("timeout", 30),
        )
