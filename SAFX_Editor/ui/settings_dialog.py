"""
Diálogo de configurações do SAFX Editor.
Abas: Geral | Exportação | SFTP | API | Aparência | Sobre
"""
import logging
import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QCheckBox, QSpinBox, QComboBox,
    QPushButton, QFileDialog, QMessageBox, QGroupBox,
    QFormLayout, QTextEdit, QFrame, QScrollArea,
    QSizePolicy, QSlider, QColorDialog,
)

from core.config import AppConfig

logger = logging.getLogger(__name__)

_NAV_BG = "#0e1b2e"
_DARK = "#1e1e2e"
_SURFACE = "#181825"
_BORDER = "#313244"
_TEXT = "#cdd6f4"
_MUTED = "#6c7086"
_ACCENT = "#89b4fa"
_GREEN = "#a6e3a1"
_RED = "#f38ba8"
_YELLOW = "#f9e2af"


def _group(title: str) -> QGroupBox:
    g = QGroupBox(title)
    g.setStyleSheet(
        f"QGroupBox{{border:1px solid {_BORDER};border-radius:6px;"
        f"margin-top:8px;padding-top:4px;color:{_ACCENT};font-weight:600;}}"
        f"QGroupBox::title{{subcontrol-origin:margin;left:10px;padding:0 4px;}}")
    return g


def _label(text: str, muted: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{'#6c7086' if muted else _TEXT};font-size:12px;")
    return lbl


def _line_edit(placeholder: str = "", password: bool = False) -> QLineEdit:
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    if password:
        le.setEchoMode(QLineEdit.EchoMode.Password)
    le.setFixedHeight(30)
    le.setStyleSheet(
        f"QLineEdit{{background:{_SURFACE};border:1px solid {_BORDER};"
        f"border-radius:5px;padding:4px 8px;color:{_TEXT};font-size:12px;}}"
        f"QLineEdit:focus{{border:1px solid {_ACCENT};}}")
    return le


def _spin(min_v: int, max_v: int, val: int) -> QSpinBox:
    sp = QSpinBox()
    sp.setRange(min_v, max_v)
    sp.setValue(val)
    sp.setFixedHeight(30)
    sp.setStyleSheet(
        f"QSpinBox{{background:{_SURFACE};border:1px solid {_BORDER};"
        f"border-radius:5px;padding:2px 6px;color:{_TEXT};font-size:12px;}}"
        f"QSpinBox:focus{{border:1px solid {_ACCENT};}}"
        f"QSpinBox::up-button,QSpinBox::down-button{{width:18px;}}")
    return sp


def _btn(text: str, color: str = _ACCENT, fg: str = _DARK,
         width: int = 120) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(30)
    b.setFixedWidth(width)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:{fg};border:none;"
        f"border-radius:5px;font-size:12px;font-weight:600;}}"
        f"QPushButton:hover{{opacity:0.85;}}"
        f"QPushButton:disabled{{background:{_BORDER};color:{_MUTED};}}")
    return b


def _check(label: str, checked: bool = False) -> QCheckBox:
    cb = QCheckBox(label)
    cb.setChecked(checked)
    cb.setStyleSheet(
        f"QCheckBox{{color:{_TEXT};font-size:12px;}}"
        f"QCheckBox::indicator{{width:16px;height:16px;"
        f"border:1px solid {_BORDER};border-radius:3px;background:{_SURFACE};}}"
        f"QCheckBox::indicator:checked{{background:{_ACCENT};border-color:{_ACCENT};}}")
    return cb


class ConnectionTestThread(QThread):
    result = pyqtSignal(bool, str)

    def __init__(self, cfg: dict):
        super().__init__()
        self._cfg = cfg

    def run(self):
        from core.sftp_manager import SFTPManager
        mgr = SFTPManager.from_config(self._cfg)
        ok, msg = mgr.test_connection()
        self.result.emit(ok, msg)


# ═══════════════════════════════════════════════════════════════════════════════
# ABAS DE CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

class TabGeral(QWidget):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        g = _group("Exibição")
        form = QFormLayout(g)
        form.setSpacing(8)

        s = self.cfg.general
        self.font_size = _spin(8, 24, s.get("font_size", 12))
        form.addRow(_label("Tamanho da fonte:"), self.font_size)

        self.page_size = _spin(50, 10000, s.get("page_size", 500))
        form.addRow(_label("Linhas por página:"), self.page_size)

        self.show_rows = _check("Mostrar números de linha", s.get("show_row_numbers", True))
        form.addRow("", self.show_rows)

        self.confirm_rollback = _check("Confirmar antes de Rollback",
                                       s.get("confirm_on_rollback", True))
        form.addRow("", self.confirm_rollback)
        layout.addWidget(g)

        g2 = _group("Consultas SQL")
        form2 = QFormLayout(g2)
        form2.setSpacing(8)

        self.auto_limit = _check("Limitar SELECT automaticamente",
                                  s.get("auto_limit_select", True))
        form2.addRow("", self.auto_limit)

        self.select_limit = _spin(100, 1000000, s.get("select_limit", 10000))
        form2.addRow(_label("Limite padrão de linhas:"), self.select_limit)
        layout.addWidget(g2)

        g3 = _group("Diretório de Layouts (MANUAL LAYOUT)")
        form3 = QFormLayout(g3)
        self.layout_dir = _line_edit("Caminho para os arquivos .md de layout")
        self.layout_dir.setText(s.get("layout_dir", ""))
        btn_browse = _btn("Procurar...", width=90)
        btn_browse.clicked.connect(self._browse_layout)
        row_ld = QHBoxLayout()
        row_ld.addWidget(self.layout_dir)
        row_ld.addWidget(btn_browse)
        form3.addRow(_label("Diretório:"), row_ld)
        layout.addWidget(g3)

        layout.addStretch()

    def _browse_layout(self):
        d = QFileDialog.getExistingDirectory(self, "Selecionar Diretório de Layouts")
        if d:
            self.layout_dir.setText(d)

    def apply(self):
        self.cfg.set_section("general", {
            "font_size": self.font_size.value(),
            "page_size": self.page_size.value(),
            "show_row_numbers": self.show_rows.isChecked(),
            "confirm_on_rollback": self.confirm_rollback.isChecked(),
            "auto_limit_select": self.auto_limit.isChecked(),
            "select_limit": self.select_limit.value(),
            "layout_dir": self.layout_dir.text(),
        })


class TabExportacao(QWidget):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        s = self.cfg.export

        g = _group("Destino Padrão de Exportação")
        form = QFormLayout(g)
        form.setSpacing(8)

        self.dest_combo = QComboBox()
        self.dest_combo.addItems([
            "Local (pasta local)",
            "Diretório de Servidor / Pasta Mapeada",
            "SFTP (configurado na aba SFTP)",
        ])
        dest_map = {"local": 0, "dir": 1, "sftp": 2}
        self.dest_combo.setCurrentIndex(dest_map.get(s.get("default_destination", "local"), 0))
        self.dest_combo.setFixedHeight(30)
        self.dest_combo.setStyleSheet(
            f"QComboBox{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:4px 8px;color:{_TEXT};}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{_DARK};color:{_TEXT};}}")
        form.addRow(_label("Destino padrão:"), self.dest_combo)

        self.local_dir = _line_edit("Ex: C:\\Exportações ou /home/user/exports")
        self.local_dir.setText(s.get("local_dir", str(Path.home() / "Downloads")))
        btn_local = _btn("Procurar...", width=90)
        btn_local.clicked.connect(lambda: self._browse(self.local_dir))
        row_local = QHBoxLayout()
        row_local.addWidget(self.local_dir)
        row_local.addWidget(btn_local)
        form.addRow(_label("Pasta local:"), row_local)

        self.server_dir = _line_edit(
            "Ex: \\\\servidor\\share\\exports  ou  /mnt/nfs/exports")
        self.server_dir.setText(s.get("server_dir", ""))
        btn_srv = _btn("Procurar...", width=90)
        btn_srv.clicked.connect(lambda: self._browse(self.server_dir))
        row_srv = QHBoxLayout()
        row_srv.addWidget(self.server_dir)
        row_srv.addWidget(btn_srv)
        form.addRow(_label("Pasta servidor:"), row_srv)

        layout.addWidget(g)

        g2 = _group("Formato do Arquivo")
        form2 = QFormLayout(g2)

        self.encoding = QComboBox()
        self.encoding.addItems(["latin-1 (padrão SAFX)", "utf-8", "cp1252"])
        enc_idx = {"latin-1": 0, "utf-8": 1, "cp1252": 2}
        self.encoding.setCurrentIndex(enc_idx.get(s.get("encoding", "latin-1"), 0))
        self.encoding.setFixedHeight(30)
        self.encoding.setStyleSheet(
            f"QComboBox{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:4px 8px;color:{_TEXT};}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{_DARK};color:{_TEXT};}}")
        form2.addRow(_label("Codificação:"), self.encoding)

        self.line_ending = QComboBox()
        self.line_ending.addItems(["CRLF (Windows / MS-DOS)", "LF (Unix/Mac)"])
        self.line_ending.setCurrentIndex(0 if s.get("line_ending", "CRLF") == "CRLF" else 1)
        self.line_ending.setFixedHeight(30)
        self.line_ending.setStyleSheet(self.encoding.styleSheet())
        form2.addRow(_label("Fim de linha:"), self.line_ending)

        self.open_after = _check("Abrir pasta após exportar",
                                  s.get("open_after_export", False))
        form2.addRow("", self.open_after)

        layout.addWidget(g2)
        layout.addStretch()

    def _browse(self, target: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Selecionar Diretório")
        if d:
            target.setText(d)

    def apply(self):
        dest_map = {0: "local", 1: "dir", 2: "sftp"}
        enc_map = {0: "latin-1", 1: "utf-8", 2: "cp1252"}
        self.cfg.set_section("export", {
            "default_destination": dest_map[self.dest_combo.currentIndex()],
            "local_dir": self.local_dir.text(),
            "server_dir": self.server_dir.text(),
            "encoding": enc_map[self.encoding.currentIndex()],
            "line_ending": "CRLF" if self.line_ending.currentIndex() == 0 else "LF",
            "open_after_export": self.open_after.isChecked(),
        })


class TabSFTP(QWidget):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self._thread = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        s = self.cfg.sftp

        self.enabled_cb = _check("Habilitar envio via SFTP", s.get("enabled", False))
        self.enabled_cb.setStyleSheet(
            f"QCheckBox{{color:{_GREEN};font-size:13px;font-weight:700;}}"
            f"QCheckBox::indicator{{width:18px;height:18px;"
            f"border:2px solid {_GREEN};border-radius:3px;background:{_SURFACE};}}"
            f"QCheckBox::indicator:checked{{background:{_GREEN};}}")
        layout.addWidget(self.enabled_cb)

        g = _group("Conexão SFTP")
        form = QFormLayout(g)
        form.setSpacing(8)

        self.host = _line_edit("Ex: sftp.adejo.com.br ou 192.168.1.100")
        self.host.setText(s.get("host", ""))
        form.addRow(_label("Host:"), self.host)

        self.port = _spin(1, 65535, s.get("port", 22))
        form.addRow(_label("Porta:"), self.port)

        self.username = _line_edit("usuário SFTP")
        self.username.setText(s.get("username", ""))
        form.addRow(_label("Usuário:"), self.username)

        self.password = _line_edit("senha", password=True)
        self.password.setText(s.get("password", ""))
        form.addRow(_label("Senha:"), self.password)

        self.key_path = _line_edit("Caminho da chave SSH privada (opcional)")
        self.key_path.setText(s.get("key_path", ""))
        btn_key = _btn("Procurar...", width=90)
        btn_key.clicked.connect(self._browse_key)
        row_key = QHBoxLayout()
        row_key.addWidget(self.key_path)
        row_key.addWidget(btn_key)
        form.addRow(_label("Chave SSH:"), row_key)

        self.remote_path = _line_edit("Ex: /home/safx/exports ou /data/incoming")
        self.remote_path.setText(s.get("remote_path", "/"))
        form.addRow(_label("Caminho remoto:"), self.remote_path)

        self.timeout = _spin(5, 120, s.get("timeout", 30))
        form.addRow(_label("Timeout (s):"), self.timeout)

        layout.addWidget(g)

        # Botão de teste
        row_test = QHBoxLayout()
        self.btn_test = _btn("Testar Conexão", _ACCENT, _DARK, 150)
        self.btn_test.clicked.connect(self._test_connection)
        row_test.addWidget(self.btn_test)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        self.test_result.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        row_test.addWidget(self.test_result)
        row_test.addStretch()
        layout.addLayout(row_test)
        layout.addStretch()

    def _browse_key(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Chave SSH Privada", "",
            "Chaves SSH (*.pem *.key *.ppk *.rsa);;Todos os arquivos (*)")
        if f:
            self.key_path.setText(f)

    def _test_connection(self):
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testando...")
        self.test_result.setText("")
        self.test_result.setStyleSheet(f"color:{_MUTED};font-size:11px;")

        cfg = {
            "host": self.host.text(),
            "port": self.port.value(),
            "username": self.username.text(),
            "password": self.password.text(),
            "key_path": self.key_path.text(),
            "remote_path": self.remote_path.text(),
            "timeout": self.timeout.value(),
        }
        self._thread = ConnectionTestThread(cfg)
        self._thread.result.connect(self._on_test_result)
        self._thread.start()

    def _on_test_result(self, ok: bool, msg: str):
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Testar Conexão")
        color = _GREEN if ok else _RED
        self.test_result.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:600;")
        self.test_result.setText(("✔ " if ok else "✖ ") + msg.split('\n')[0])

    def apply(self):
        self.cfg.set_section("sftp", {
            "enabled": self.enabled_cb.isChecked(),
            "host": self.host.text(),
            "port": self.port.value(),
            "username": self.username.text(),
            "password": self.password.text(),
            "key_path": self.key_path.text(),
            "remote_path": self.remote_path.text(),
            "timeout": self.timeout.value(),
        })


class TabAPI(QWidget):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        s = self.cfg.api

        self.enabled_cb = _check("Habilitar servidor REST API", s.get("enabled", False))
        self.enabled_cb.setStyleSheet(
            f"QCheckBox{{color:{_YELLOW};font-size:13px;font-weight:700;}}"
            f"QCheckBox::indicator{{width:18px;height:18px;"
            f"border:2px solid {_YELLOW};border-radius:3px;background:{_SURFACE};}}"
            f"QCheckBox::indicator:checked{{background:{_YELLOW};}}")
        layout.addWidget(self.enabled_cb)

        g = _group("Configuração do Servidor")
        form = QFormLayout(g)
        form.setSpacing(8)

        self.host = QComboBox()
        self.host.setEditable(True)
        self.host.addItems(["0.0.0.0 (todas as interfaces)", "127.0.0.1 (somente local)"])
        h = s.get("host", "0.0.0.0")
        self.host.setCurrentText(h if h in ("0.0.0.0", "127.0.0.1") else h)
        self.host.setFixedHeight(30)
        self.host.setStyleSheet(
            f"QComboBox{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:4px 8px;color:{_TEXT};}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{_DARK};color:{_TEXT};}}")
        form.addRow(_label("Interface:"), self.host)

        self.port = _spin(1024, 65535, s.get("port", 8787))
        form.addRow(_label("Porta:"), self.port)

        self.api_key = _line_edit("Deixe vazio para sem autenticação", password=False)
        self.api_key.setText(s.get("api_key", ""))
        btn_gen = _btn("Gerar", _SURFACE, _ACCENT, 70)
        btn_gen.clicked.connect(self._gen_key)
        row_key = QHBoxLayout()
        row_key.addWidget(self.api_key)
        row_key.addWidget(btn_gen)
        form.addRow(_label("API Key (X-API-Key):"), row_key)

        self.read_only = _check("Modo somente leitura (bloqueia UPDATE/INSERT via API)",
                                 s.get("read_only", False))
        form.addRow("", self.read_only)

        self.log_requests = _check("Registrar requisições no log",
                                    s.get("log_requests", True))
        form.addRow("", self.log_requests)

        layout.addWidget(g)

        # Endpoints documentation
        g2 = _group("Endpoints Disponíveis")
        doc = QTextEdit()
        doc.setReadOnly(True)
        doc.setFixedHeight(160)
        port = s.get("port", 8787)
        doc.setPlainText(
            f"GET  http://localhost:{port}/api/health\n"
            f"GET  http://localhost:{port}/api/tables\n"
            f"GET  http://localhost:{port}/api/tables/{{tabela}}/data?limit=100&CAMPO=valor\n"
            f"GET  http://localhost:{port}/api/tables/{{tabela}}/count\n"
            f"GET  http://localhost:{port}/api/tables/{{tabela}}/schema\n"
            f"POST http://localhost:{port}/api/tables/{{tabela}}/update\n"
            f"POST http://localhost:{port}/api/sql\n\n"
            f"Header de autenticação: X-API-Key: <sua-chave>\n\n"
            f"Exemplo UPDATE:\n"
            f'POST /api/tables/SAFX07/update\n'
            f'{{"rows": [{{"_row_id": 1, "VLR_ITEM": "00000000000100000"}}]}}'
        )
        doc.setStyleSheet(
            f"QTextEdit{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;color:{_MUTED};font-family:Consolas;font-size:11px;"
            f"padding:6px;}}")
        g2v = QVBoxLayout(g2)
        g2v.addWidget(doc)
        layout.addWidget(g2)
        layout.addStretch()

    def _gen_key(self):
        import secrets
        self.api_key.setText(secrets.token_urlsafe(24))

    def apply(self):
        h = self.host.currentText().split(' ')[0]
        self.cfg.set_section("api", {
            "enabled": self.enabled_cb.isChecked(),
            "host": h,
            "port": self.port.value(),
            "api_key": self.api_key.text(),
            "read_only": self.read_only.isChecked(),
            "log_requests": self.log_requests.isChecked(),
        })


class TabAparencia(QWidget):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        b = self.cfg.branding

        g = _group("Marca / Identidade Visual")
        form = QFormLayout(g)
        form.setSpacing(8)

        self.company = _line_edit("Nome da empresa")
        self.company.setText(b.get("company_name", "Adejo Desenvolvimento"))
        form.addRow(_label("Nome da empresa:"), self.company)

        self.show_logo = _check("Exibir logo no cabeçalho",
                                 b.get("show_logo", True))
        form.addRow("", self.show_logo)

        self.logo_path = _line_edit("Caminho para PNG/SVG do logo personalizado")
        self.logo_path.setText(b.get("logo_path", ""))
        btn_logo = _btn("Selecionar...", width=100)
        btn_logo.clicked.connect(self._browse_logo)
        row_logo = QHBoxLayout()
        row_logo.addWidget(self.logo_path)
        row_logo.addWidget(btn_logo)
        form.addRow(_label("Logo personalizado:"), row_logo)

        # Cor de destaque
        self.accent_preview = QLabel("  ■  Cor de Destaque")
        self._set_preview_color(b.get("accent_color", "#89b4fa"))
        btn_accent = _btn("Alterar...", width=90)
        btn_accent.clicked.connect(self._pick_accent)
        row_acc = QHBoxLayout()
        row_acc.addWidget(self.accent_preview)
        row_acc.addWidget(btn_accent)
        row_acc.addStretch()
        form.addRow(_label("Cor de destaque:"), row_acc)

        layout.addWidget(g)

        # Preview do cabeçalho
        g2 = _group("Preview do Cabeçalho")
        g2v = QVBoxLayout(g2)
        self.preview_header = QLabel()
        self.preview_header.setFixedHeight(60)
        self.preview_header.setStyleSheet(
            f"background:{_NAV_BG};border-radius:6px;padding:8px;")
        self.preview_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_header.setText("[ Logo Adejo ] — SAFX Editor")
        self.preview_header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.preview_header.setStyleSheet(
            f"background:{_NAV_BG};border-radius:6px;"
            f"color:white;font-size:14px;font-weight:bold;padding:10px;")
        g2v.addWidget(self.preview_header)
        layout.addWidget(g2)

        lbl_note = _label(
            "Nota: Algumas alterações de aparência requerem reiniciar o aplicativo.",
            muted=True)
        layout.addWidget(lbl_note)
        layout.addStretch()

        self._accent_color = b.get("accent_color", "#89b4fa")

    def _browse_logo(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Logo", "",
            "Imagens (*.png *.jpg *.jpeg *.svg *.ico);;Todos os arquivos (*)")
        if f:
            self.logo_path.setText(f)

    def _pick_accent(self):
        c = QColorDialog.getColor(QColor(self._accent_color), self,
                                   "Escolher cor de destaque")
        if c.isValid():
            self._accent_color = c.name()
            self._set_preview_color(self._accent_color)

    def _set_preview_color(self, color: str):
        self._accent_color = color
        self.accent_preview = getattr(self, 'accent_preview',
                                       QLabel("  ■  Cor de Destaque"))
        self.accent_preview.setStyleSheet(
            f"color:{color};font-size:13px;font-weight:700;"
            f"background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:4px;padding:4px 8px;")

    def apply(self):
        self.cfg.set_section("branding", {
            "company_name": self.company.text(),
            "show_logo": self.show_logo.isChecked(),
            "logo_path": self.logo_path.text(),
            "accent_color": self._accent_color,
        })


class TabSobre(QWidget):
    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 32, 32, 32)

        # Logo
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                  "assets", "adejo_logo.png")
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(
                160, 80, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        else:
            logo_lbl.setText("ADEJO")
            logo_lbl.setStyleSheet(
                f"color:white;font-size:32px;font-weight:900;"
                f"background:{_NAV_BG};border-radius:12px;padding:16px 32px;")
        layout.addWidget(logo_lbl)

        lbl_product = QLabel("SAFX Editor")
        lbl_product.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_product.setStyleSheet(
            f"color:{_TEXT};font-size:22px;font-weight:700;")
        layout.addWidget(lbl_product)

        lbl_version = QLabel("Versão 1.0.0  |  Adejo Desenvolvimento")
        lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_version.setStyleSheet(f"color:{_MUTED};font-size:12px;")
        layout.addWidget(lbl_version)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{_BORDER};")
        layout.addWidget(sep)

        desc = QLabel(
            "Sistema de importação, ajuste e exportação de tabelas SAFX.\n"
            "Suporte a arquivos com milhões de linhas, editor SQL completo\n"
            "com transações, exportação CSV homologada, API REST e SFTP."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"color:{_MUTED};font-size:12px;line-height:1.6;")
        layout.addWidget(desc)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{_BORDER};")
        layout.addWidget(sep2)

        lbl_tech = QLabel(
            "Python 3 · PyQt6 · SQLite · paramiko · Flask"
        )
        lbl_tech.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_tech.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        layout.addWidget(lbl_tech)

        lbl_copy = QLabel("© 2026 Adejo Desenvolvimento. Todos os direitos reservados.")
        lbl_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_copy.setStyleSheet(f"color:{_MUTED};font-size:10px;")
        layout.addWidget(lbl_copy)

        layout.addStretch()


# ═══════════════════════════════════════════════════════════════════════════════
# DIÁLOGO PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """Diálogo de configurações com abas."""

    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = AppConfig.get()
        self.setWindowTitle("Configurações — SAFX Editor")
        self.setMinimumSize(720, 560)
        self.setStyleSheet(
            f"QDialog{{background:{_DARK};}}"
            f"QTabWidget::pane{{border:1px solid {_BORDER};"
            f"background:{_DARK};border-radius:6px;}}"
            f"QTabBar::tab{{background:{_SURFACE};color:{_MUTED};"
            f"padding:8px 18px;border:none;border-radius:4px 4px 0 0;"
            f"font-size:12px;margin-right:2px;}}"
            f"QTabBar::tab:selected{{background:{_DARK};color:{_ACCENT};"
            f"font-weight:700;}}"
            f"QTabBar::tab:hover{{color:{_TEXT};}}"
            f"QScrollArea{{border:none;}}")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background:{_NAV_BG};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)

        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                  "assets", "adejo_logo.png")
        if os.path.exists(logo_path):
            logo_lbl = QLabel()
            pix = QPixmap(logo_path).scaled(
                80, 32, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            hl.addWidget(logo_lbl)
        else:
            hl.addWidget(QLabel("ADEJO"))

        lbl = QLabel("  Configurações do Sistema")
        lbl.setStyleSheet("color:white;font-size:14px;font-weight:700;")
        hl.addWidget(lbl)
        hl.addStretch()
        layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_geral = TabGeral(self.cfg)
        self.tab_export = TabExportacao(self.cfg)
        self.tab_sftp = TabSFTP(self.cfg)
        self.tab_api = TabAPI(self.cfg)
        self.tab_aparencia = TabAparencia(self.cfg)
        self.tab_sobre = TabSobre()

        self.tabs.addTab(self.tab_geral, "⚙ Geral")
        self.tabs.addTab(self.tab_export, "📁 Exportação")
        self.tabs.addTab(self.tab_sftp, "🔒 SFTP")
        self.tabs.addTab(self.tab_api, "🌐 API REST")
        self.tabs.addTab(self.tab_aparencia, "🎨 Aparência")
        self.tabs.addTab(self._build_tab_layout_editor(), "📐 Layout SAFX")
        self.tabs.addTab(self._build_tab_ext_db(), "🗄 Banco Externo")
        self.tabs.addTab(self.tab_sobre, "ℹ Sobre")

        layout.addWidget(self.tabs)

        # Footer com botões
        footer = QWidget()
        footer.setFixedHeight(52)
        footer.setStyleSheet(
            f"background:{_SURFACE};border-top:1px solid {_BORDER};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 0, 16, 0)
        fl.setSpacing(8)

        btn_reset = _btn("Restaurar padrões", _SURFACE, _RED, 150)
        btn_reset.setStyleSheet(
            f"QPushButton{{background:{_SURFACE};color:{_RED};"
            f"border:1px solid {_RED};border-radius:5px;font-size:12px;}}"
            f"QPushButton:hover{{background:{_RED};color:white;}}")
        btn_reset.clicked.connect(self._reset)
        fl.addWidget(btn_reset)

        fl.addStretch()

        btn_cancel = _btn("Cancelar", _SURFACE, _MUTED, 100)
        btn_cancel.setStyleSheet(
            f"QPushButton{{background:{_SURFACE};color:{_MUTED};"
            f"border:1px solid {_BORDER};border-radius:5px;font-size:12px;}}"
            f"QPushButton:hover{{color:{_TEXT};}}")
        btn_cancel.clicked.connect(self.reject)
        fl.addWidget(btn_cancel)

        btn_ok = _btn("Salvar e Fechar", _ACCENT, _DARK, 130)
        btn_ok.clicked.connect(self._apply_and_close)
        fl.addWidget(btn_ok)

        layout.addWidget(footer)

    def _apply_and_close(self):
        self.tab_geral.apply()
        self.tab_export.apply()
        self.tab_sftp.apply()
        self.tab_api.apply()
        self.tab_aparencia.apply()
        self.settings_changed.emit()
        self.accept()

    def _reset(self):
        reply = QMessageBox.question(
            self, "Restaurar Padrões",
            "Isso irá restaurar TODAS as configurações para os valores padrão.\n"
            "Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.cfg.reset_all()
            self.close()
            dlg = SettingsDialog(self.parent())
            dlg.exec()

    # ─── Aba: Editor de Layout SAFX ───────────────────────────────────────────

    def _build_tab_layout_editor(self) -> QWidget:
        """
        Permite adicionar, remover e editar campos de qualquer tabela SAFX.
        Os layouts padrão (MANUAL LAYOUT) são mantidos — apenas extensões
        personalizadas são salvas na configuração.
        """
        from PyQt6.QtWidgets import (
            QTableWidget, QTableWidgetItem, QHeaderView,
            QSplitter, QListWidget, QListWidgetItem
        )
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        info = QLabel(
            "ℹ  Os layouts padrão das tabelas SAFX são mantidos intactos.\n"
            "Aqui você pode adicionar campos extras ou personalizar campos específicos.\n"
            "As alterações são salvas em: ~/.safx_editor/custom_layouts.json")
        info.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Lista de tabelas SAFX
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Tabelas SAFX:"))
        self._layout_list = QListWidget()
        self._layout_list.setFixedWidth(160)
        known_safx = [f'SAFX{n}' for n in [
            '01','04','05','07','08','14','21','24','25','30','31','34','35',
            '40','41','50','51','54','55','60','64','65','71','75','82','83',
            '92','93','96','97','108','109','118','119','128','139','148',
            '158','159','168','169','299','431','501','520','534','540',
            '702','992','993','2089','2098','2099']]
        for t in known_safx:
            self._layout_list.addItem(QListWidgetItem(t))
        self._layout_list.currentTextChanged.connect(self._on_layout_table_selected)
        ll.addWidget(self._layout_list)
        splitter.addWidget(left)

        # Editor de campos
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        rl.addWidget(QLabel("Campos personalizados (adicionar além do padrão):"))

        self._layout_table = QTableWidget(0, 5)
        self._layout_table.setHorizontalHeaderLabels(
            ["Campo", "Tipo (alfa/num/date)", "Tamanho", "Decimais", "Obrig."])
        for i, w_col in enumerate([180, 120, 80, 80, 60]):
            self._layout_table.setColumnWidth(i, w_col)
        self._layout_table.setStyleSheet(
            f"QTableWidget{{background:{_DARK};color:{_TEXT};"
            f"gridline-color:{_BORDER};border:1px solid {_BORDER};}}"
            f"QHeaderView::section{{background:#26263a;color:{_ACCENT};"
            f"font-weight:700;padding:5px;border:none;}}")
        rl.addWidget(self._layout_table, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Adicionar Campo")
        btn_add.setFixedHeight(30)
        btn_add.clicked.connect(self._layout_add_field)
        btn_row.addWidget(btn_add)

        btn_del = QPushButton("− Remover Selecionado")
        btn_del.setFixedHeight(30)
        btn_del.clicked.connect(self._layout_remove_field)
        btn_row.addWidget(btn_del)

        btn_save = QPushButton("💾  Salvar Personalização")
        btn_save.setFixedHeight(30)
        btn_save.setStyleSheet(
            f"QPushButton{{background:#1a4e1a;color:{_GREEN};"
            f"border:1px solid #2a7a2a;border-radius:5px;font-weight:700;}}"
            f"QPushButton:hover{{background:#2a7a2a;color:white;}}")
        btn_save.clicked.connect(self._layout_save)
        btn_row.addWidget(btn_save)

        rl.addLayout(btn_row)

        self._lbl_layout_status = QLabel("")
        self._lbl_layout_status.setStyleSheet(f"color:{_GREEN};font-size:11px;")
        rl.addWidget(self._lbl_layout_status)

        splitter.addWidget(right)
        splitter.setSizes([160, 600])
        lay.addWidget(splitter, 1)
        return w

    def _on_layout_table_selected(self, table_name: str):
        """Carrega campos personalizados salvos para a tabela."""
        self._current_layout_table = table_name
        custom = self.cfg.get_value('custom_layouts', table_name, [])
        self._layout_table.setRowCount(0)
        for field in custom:
            self._layout_add_field_data(field)
        self._lbl_layout_status.setText(
            f"Campos personalizados para {table_name}: {len(custom)}")

    def _layout_add_field(self):
        from PyQt6.QtWidgets import QTableWidgetItem, QComboBox
        row = self._layout_table.rowCount()
        self._layout_table.setRowCount(row + 1)
        self._layout_table.setItem(row, 0, QTableWidgetItem("NOVO_CAMPO"))
        self._layout_table.setItem(row, 1, QTableWidgetItem("alfa"))
        self._layout_table.setItem(row, 2, QTableWidgetItem("50"))
        self._layout_table.setItem(row, 3, QTableWidgetItem("0"))
        self._layout_table.setItem(row, 4, QTableWidgetItem("N"))

    def _layout_add_field_data(self, field: dict):
        from PyQt6.QtWidgets import QTableWidgetItem
        row = self._layout_table.rowCount()
        self._layout_table.setRowCount(row + 1)
        self._layout_table.setItem(row, 0, QTableWidgetItem(field.get('name', '')))
        self._layout_table.setItem(row, 1, QTableWidgetItem(field.get('type', 'alfa')))
        self._layout_table.setItem(row, 2, QTableWidgetItem(str(field.get('size', 50))))
        self._layout_table.setItem(row, 3, QTableWidgetItem(str(field.get('decimals', 0))))
        self._layout_table.setItem(row, 4, QTableWidgetItem(field.get('mandatory', 'N')))

    def _layout_remove_field(self):
        row = self._layout_table.currentRow()
        if row >= 0:
            self._layout_table.removeRow(row)

    def _layout_save(self):
        table_name = getattr(self, '_current_layout_table', None)
        if not table_name:
            QMessageBox.warning(self, "Atenção", "Selecione uma tabela primeiro.")
            return
        fields = []
        for r in range(self._layout_table.rowCount()):
            fields.append({
                'name':      (self._layout_table.item(r, 0) or _ti('')).text().strip(),
                'type':      (self._layout_table.item(r, 1) or _ti('')).text().strip() or 'alfa',
                'size':      int((self._layout_table.item(r, 2) or _ti('50')).text() or '50'),
                'decimals':  int((self._layout_table.item(r, 3) or _ti('0')).text() or '0'),
                'mandatory': (self._layout_table.item(r, 4) or _ti('N')).text().strip() or 'N',
            })
        self.cfg.set_value('custom_layouts', table_name, fields)
        self._lbl_layout_status.setText(
            f"✔  {len(fields)} campo(s) salvos para {table_name}")

    # ─── Aba: Banco Externo Opcional ──────────────────────────────────────────

    def _build_tab_ext_db(self) -> QWidget:
        from PyQt6.QtWidgets import QTableWidget, QHeaderView
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        info = QLabel(
            "ℹ  Banco externo OPCIONAL — o sistema funciona normalmente sem ele.\n"
            "Configure para persistir dados, change log e histórico entre sessões.\n"
            "Suporte: SQLite local  •  PostgreSQL  •  Supabase  •  Oracle  •  MySQL")
        info.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        # Habilitar banco externo
        self.chk_ext_db = QCheckBox("Habilitar banco de dados externo para persistência")
        self.chk_ext_db.setChecked(self.cfg.get_value('ext_db', 'enabled', False))
        self.chk_ext_db.toggled.connect(self._on_ext_db_toggle)
        lay.addWidget(self.chk_ext_db)

        gb = QGroupBox("Configuração do Banco")
        gb.setStyleSheet(
            f"QGroupBox{{color:{_ACCENT};font-size:12px;font-weight:700;"
            f"border:1px solid {_BORDER};border-radius:6px;"
            f"margin-top:8px;padding:14px 10px 10px 10px;}}"
            f"QGroupBox::title{{padding:0 6px;}}")
        gl = QFormLayout(gb)
        gl.setSpacing(8)
        gl.setContentsMargins(10, 14, 10, 10)
        gl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _row(lbl_txt, widget):
            lbl = QLabel(lbl_txt)
            lbl.setStyleSheet(f"color:{_MUTED};font-size:12px;")
            gl.addRow(lbl, widget)

        self.combo_ext_type = QComboBox()
        for key, name in [('sqlite', 'SQLite (arquivo local)'),
                          ('postgres', 'PostgreSQL'),
                          ('supabase', 'Supabase (PostgreSQL)'),
                          ('oracle', 'Oracle Database'),
                          ('mysql', 'MySQL / MariaDB')]:
            self.combo_ext_type.addItem(name, userData=key)
        self.combo_ext_type.setFixedHeight(32)
        _row("Tipo:", self.combo_ext_type)

        self.edit_ext_host = QLineEdit()
        self.edit_ext_host.setFixedHeight(30)
        self.edit_ext_host.setPlaceholderText("host ou caminho SQLite")
        _row("Host/Arquivo:", self.edit_ext_host)

        self.spin_ext_port = QSpinBox()
        self.spin_ext_port.setRange(0, 65535)
        self.spin_ext_port.setFixedHeight(30)
        _row("Porta:", self.spin_ext_port)

        self.edit_ext_db = QLineEdit()
        self.edit_ext_db.setFixedHeight(30)
        self.edit_ext_db.setPlaceholderText("database / schema / service_name")
        _row("Database:", self.edit_ext_db)

        self.edit_ext_user = QLineEdit()
        self.edit_ext_user.setFixedHeight(30)
        _row("Usuário:", self.edit_ext_user)

        self.edit_ext_pw = QLineEdit()
        self.edit_ext_pw.setFixedHeight(30)
        self.edit_ext_pw.setEchoMode(QLineEdit.EchoMode.Password)
        _row("Senha:", self.edit_ext_pw)

        self.chk_persist_safx = QCheckBox(
            "Salvar tabelas SAFX importadas no banco externo")
        self.chk_persist_safx.setChecked(
            self.cfg.get_value('ext_db', 'persist_tables', False))
        gl.addWidget(self.chk_persist_safx)

        self.chk_persist_log = QCheckBox(
            "Salvar change log no banco externo (sempre recomendado)")
        self.chk_persist_log.setChecked(
            self.cfg.get_value('ext_db', 'persist_log', True))
        gl.addWidget(self.chk_persist_log)

        lay.addWidget(gb)

        # Scripts DDL
        gb_scripts = QGroupBox("Scripts de Criação das Tabelas")
        gb_scripts.setStyleSheet(gb.styleSheet())
        sl = QVBoxLayout(gb_scripts)
        sl.addWidget(QLabel(
            "Baixe o script SQL para criar as tabelas no seu banco antes de conectar:"))

        scripts_row = QHBoxLayout()
        for db_type, label in [('postgres', 'PostgreSQL/Supabase'),
                                ('oracle', 'Oracle'), ('mysql', 'MySQL'),
                                ('sqlite', 'SQLite')]:
            btn = QPushButton(f"⬇ {label}")
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, t=db_type: self._save_ddl_script(t))
            scripts_row.addWidget(btn)
        sl.addLayout(scripts_row)

        lay.addWidget(gb_scripts)

        # Testar conexão + salvar
        btn_row = QHBoxLayout()

        btn_test = QPushButton("🔌 Testar Conexão")
        btn_test.setFixedHeight(32)
        btn_test.clicked.connect(self._test_ext_db)
        btn_row.addWidget(btn_test)

        btn_save_ext = QPushButton("💾 Salvar")
        btn_save_ext.setFixedHeight(32)
        btn_save_ext.setStyleSheet(
            f"QPushButton{{background:#1a4e1a;color:{_GREEN};"
            f"border:1px solid #2a7a2a;border-radius:5px;font-weight:700;}}"
            f"QPushButton:hover{{background:#2a7a2a;color:white;}}")
        btn_save_ext.clicked.connect(self._save_ext_db_settings)
        btn_row.addWidget(btn_save_ext)

        lay.addLayout(btn_row)

        self.lbl_ext_db_status = QLabel("")
        self.lbl_ext_db_status.setWordWrap(True)
        lay.addWidget(self.lbl_ext_db_status)

        lay.addStretch()
        self._load_ext_db_settings()
        return w

    def _on_ext_db_toggle(self, checked: bool):
        self.cfg.set_value('ext_db', 'enabled', checked)

    def _load_ext_db_settings(self):
        cfg = self.cfg.get_section('ext_db')
        if isinstance(cfg, dict):
            self.edit_ext_host.setText(cfg.get('host', ''))
            self.spin_ext_port.setValue(cfg.get('port', 5432))
            self.edit_ext_db.setText(cfg.get('database', ''))
            self.edit_ext_user.setText(cfg.get('username', ''))
            db_type = cfg.get('type', 'sqlite')
            for i in range(self.combo_ext_type.count()):
                if self.combo_ext_type.itemData(i) == db_type:
                    self.combo_ext_type.setCurrentIndex(i)
                    break

    def _save_ext_db_settings(self):
        self.cfg.set_section('ext_db', {
            'enabled': self.chk_ext_db.isChecked(),
            'type':    self.combo_ext_type.currentData(),
            'host':    self.edit_ext_host.text(),
            'port':    self.spin_ext_port.value(),
            'database': self.edit_ext_db.text(),
            'username': self.edit_ext_user.text(),
            'password': self.edit_ext_pw.text(),
            'persist_tables': self.chk_persist_safx.isChecked(),
            'persist_log':    self.chk_persist_log.isChecked(),
        })
        self.lbl_ext_db_status.setText("✔ Configurações salvas.")
        self.lbl_ext_db_status.setStyleSheet(f"color:{_GREEN};font-size:11px;")

    def _test_ext_db(self):
        from core.external_db import ExternalDBManager
        mgr = ExternalDBManager()
        db_type = self.combo_ext_type.currentData()
        ok, msg = mgr.connect(
            db_type,
            host=self.edit_ext_host.text(),
            port=self.spin_ext_port.value(),
            dbname=self.edit_ext_db.text(),
            user=self.edit_ext_user.text(),
            password=self.edit_ext_pw.text(),
            path=self.edit_ext_host.text()
        )
        mgr.disconnect()
        color = _GREEN if ok else '#f38ba8'
        self.lbl_ext_db_status.setText(f"{'✔' if ok else '✗'}  {msg}")
        self.lbl_ext_db_status.setStyleSheet(f"color:{color};font-size:11px;")

    def _save_ddl_script(self, db_type: str):
        from PyQt6.QtWidgets import QFileDialog
        from core.external_db import save_ddl_script, DDL_SCRIPT_NAMES
        import os
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar pasta para salvar o script SQL",
            os.path.expanduser('~'))
        if not folder:
            return
        path = save_ddl_script(db_type, folder)
        QMessageBox.information(
            self, "Script Salvo",
            f"✔  Script DDL salvo em:\n{path}\n\n"
            f"Execute este arquivo no banco de dados antes de conectar o SAFX Editor.")


def _ti(txt: str):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem(txt)
