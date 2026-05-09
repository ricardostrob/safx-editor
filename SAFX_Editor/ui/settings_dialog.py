"""
Diálogo de configurações do SAFX Editor.
Abas: Geral | Exportação | SFTP | API | Aparência | Sobre
"""
import copy
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
    QSizePolicy, QSlider, QColorDialog, QListWidget, QListWidgetItem,
)

from typing import Any, Dict, List, Optional

from core.config import AppConfig

logger = logging.getLogger(__name__)

_NAV_BG  = "#0e1b2e"
_DARK    = "#1e1e2e"
_SURFACE = "#181825"
_BORDER  = "#313244"
_TEXT    = "#cdd6f4"
_MUTED   = "#6c7086"
_ACCENT  = "#89b4fa"
_GREEN   = "#a6e3a1"
_RED     = "#f38ba8"
_YELLOW  = "#f9e2af"


def _apply_settings_theme(is_dark: bool):
    """Atualiza as constantes de cores globais do módulo conforme o tema."""
    global _NAV_BG, _DARK, _SURFACE, _BORDER, _TEXT, _MUTED, _ACCENT
    if is_dark:
        _NAV_BG  = "#0e1b2e"; _DARK    = "#1e1e2e"; _SURFACE = "#181825"
        _BORDER  = "#313244"; _TEXT    = "#cdd6f4"; _MUTED   = "#6c7086"
        _ACCENT  = "#89b4fa"
    else:
        _NAV_BG  = "#1a3a6e"; _DARK    = "#f0f2f5"; _SURFACE = "#ffffff"
        _BORDER  = "#c0c5d4"; _TEXT    = "#1a1a2e"; _MUTED   = "#555a70"
        _ACCENT  = "#1a5faa"


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

        self.combo_export_sftp = QComboBox()
        self.combo_export_sftp.setFixedHeight(30)
        self.combo_export_sftp.setStyleSheet(
            f"QComboBox{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:4px 8px;color:{_TEXT};}}"
            f"QComboBox QAbstractItemView{{background:{_DARK};color:{_TEXT};}}")
        self._reload_export_sftp_combo()
        exp_sp = s.get("sftp_profile_id", "") or ""
        for i in range(self.combo_export_sftp.count()):
            if str(self.combo_export_sftp.itemData(i) or "") == str(exp_sp):
                self.combo_export_sftp.setCurrentIndex(i)
                break
        form.addRow(_label("Perfil SFTP (exportação):"), self.combo_export_sftp)
        tip_sf = QLabel(
            "Se vazio, usa o perfil selecionado na aba SFTP. Caso contrário, envia "
            "sempre por este perfil ao escolher destino SFTP na exportação.")
        tip_sf.setStyleSheet(f"color:{_MUTED};font-size:10px;")
        tip_sf.setWordWrap(True)
        form.addRow("", tip_sf)

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
        sftp_pid = ""
        if hasattr(self, "combo_export_sftp") and self.combo_export_sftp.count() > 0:
            sftp_pid = str(self.combo_export_sftp.currentData() or "")
        self.cfg.set_section("export", {
            "default_destination": dest_map[self.dest_combo.currentIndex()],
            "local_dir": self.local_dir.text(),
            "server_dir": self.server_dir.text(),
            "encoding": enc_map[self.encoding.currentIndex()],
            "line_ending": "CRLF" if self.line_ending.currentIndex() == 0 else "LF",
            "open_after_export": self.open_after.isChecked(),
            "sftp_profile_id": sftp_pid,
        })

    def _reload_export_sftp_combo(self):
        self.combo_export_sftp.clear()
        self.combo_export_sftp.addItem("(Perfil ativo da aba SFTP)", userData="")
        for p in self.cfg.list_sftp_profiles():
            pid = str(p.get("id", ""))
            nm = str(p.get("name", ""))
            host = str(p.get("host", ""))
            self.combo_export_sftp.addItem(f"{nm} — {host}", userData=pid)


class TabSFTP(QWidget):
    """Vários perfis SFTP (ex.: um por base do cliente)."""

    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self._thread = None
        self._profiles: List[Dict[str, Any]] = cfg.list_sftp_profiles()
        self._suppress_list = False
        self._build()

    def _build(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(14)

        left = QVBoxLayout()
        left.addWidget(_label("Perfis (selecione para editar)"))
        self.profile_list = QListWidget()
        self.profile_list.setMinimumWidth(210)
        self.profile_list.setMaximumWidth(300)
        self.profile_list.setStyleSheet(
            f"QListWidget{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:6px;color:{_TEXT};padding:4px;}}"
            f"QListWidget::item{{padding:8px;border-radius:4px;}}"
            f"QListWidget::item:selected{{background:{_ACCENT};color:{_DARK};}}")
        self._refill_profile_list()
        self.profile_list.currentRowChanged.connect(self._on_profile_row_changed)
        left.addWidget(self.profile_list)

        row_btns = QHBoxLayout()
        b_new = _btn("+ Novo", _SURFACE, _ACCENT, 70)
        b_new.clicked.connect(self._new_profile)
        b_dup = _btn("Duplicar", _SURFACE, _TEXT, 78)
        b_dup.clicked.connect(self._dup_profile)
        b_del = _btn("Excluir", _SURFACE, _RED, 72)
        b_del.clicked.connect(self._del_profile)
        row_btns.addWidget(b_new)
        row_btns.addWidget(b_dup)
        row_btns.addWidget(b_del)
        left.addLayout(row_btns)

        tip = QLabel(
            "Cada perfil guarda host, credenciais e pasta remota.\n"
            "Na Exportação escolha qual perfil usar ao enviar por SFTP.\n"
            "Após alterar a senha, use «Salvar e Fechar» — o teste usa só o formulário.")
        tip.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        tip.setWordWrap(True)
        left.addWidget(tip)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(10)

        self.profile_name = _line_edit("Nome do perfil (ex.: Cliente A — produção)")
        row_nm = QFormLayout()
        row_nm.addRow(_label("Nome:"), self.profile_name)
        right.addLayout(row_nm)

        self.enabled_cb = _check("Habilitar envio via SFTP neste perfil", False)
        self.enabled_cb.setStyleSheet(
            f"QCheckBox{{color:{_GREEN};font-size:13px;font-weight:700;}}"
            f"QCheckBox::indicator{{width:18px;height:18px;"
            f"border:2px solid {_GREEN};border-radius:3px;background:{_SURFACE};}}"
            f"QCheckBox::indicator:checked{{background:{_GREEN};}}")
        right.addWidget(self.enabled_cb)

        g = _group("Conexão SFTP")
        form = QFormLayout(g)
        form.setSpacing(8)

        self.host = _line_edit("Ex: sftp.adejo.com.br ou 192.168.1.100")
        form.addRow(_label("Host:"), self.host)

        self.port = _spin(1, 65535, 22)
        form.addRow(_label("Porta:"), self.port)

        self.username = _line_edit("usuário SFTP")
        form.addRow(_label("Usuário:"), self.username)

        self.password = _line_edit("senha", password=True)
        form.addRow(_label("Senha:"), self.password)

        self.key_path = _line_edit("Caminho da chave SSH privada (opcional)")
        btn_key = _btn("Procurar...", width=90)
        btn_key.clicked.connect(self._browse_key)
        row_key = QHBoxLayout()
        row_key.addWidget(self.key_path)
        row_key.addWidget(btn_key)
        form.addRow(_label("Chave SSH:"), row_key)

        self.remote_path = _line_edit("Ex: /home/safx/exports ou /data/incoming")
        form.addRow(_label("Caminho remoto:"), self.remote_path)

        self.timeout = _spin(5, 120, 30)
        form.addRow(_label("Timeout (s):"), self.timeout)

        right.addWidget(g)

        row_test = QHBoxLayout()
        self.btn_test = _btn("Testar Conexão", _ACCENT, _DARK, 150)
        self.btn_test.clicked.connect(self._test_connection)
        row_test.addWidget(self.btn_test)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        self.test_result.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        row_test.addWidget(self.test_result)
        row_test.addStretch()
        right.addLayout(row_test)
        right.addStretch()

        main.addLayout(left, 0)
        main.addLayout(right, 1)

        self._select_active_profile_row()
        self._prev_row = self.profile_list.currentRow()

    def _pid_at_row(self, row: int) -> Optional[str]:
        it = self.profile_list.item(row)
        if not it:
            return None
        return str(it.data(Qt.ItemDataRole.UserRole) or "")

    def _refill_profile_list(self):
        self.profile_list.clear()
        for p in self._profiles:
            pid = str(p.get("id", ""))
            nm = str(p.get("name") or "Sem nome")
            host = str(p.get("host") or "")
            item = QListWidgetItem(f"{nm}\n{host}")
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self.profile_list.addItem(item)

    def _select_active_profile_row(self):
        aid = self.cfg.get_sftp_active_profile_id()
        self._suppress_list = True
        for i in range(self.profile_list.count()):
            if self._pid_at_row(i) == aid:
                self.profile_list.setCurrentRow(i)
                break
        else:
            if self.profile_list.count() > 0:
                self.profile_list.setCurrentRow(0)
        self._suppress_list = False
        self._load_form_from_profile(self.profile_list.currentRow())

    def _on_profile_row_changed(self, row: int):
        if self._suppress_list or row < 0:
            return
        prev = getattr(self, "_prev_row", -1)
        if prev >= 0 and prev != row:
            self._save_form_into_profile_by_row(prev)
        self._prev_row = row
        self._load_form_from_profile(row)

    def _profile_index_by_id(self, pid: str) -> int:
        for i, p in enumerate(self._profiles):
            if str(p.get("id")) == pid:
                return i
        return -1

    def _save_form_into_profile_by_row(self, row: int):
        pid = self._pid_at_row(row)
        if not pid:
            return
        idx = self._profile_index_by_id(pid)
        if idx < 0:
            return
        p = self._profiles[idx]
        p["name"] = self.profile_name.text().strip() or p.get("name", "Perfil")
        p["enabled"] = self.enabled_cb.isChecked()
        p["host"] = self.host.text()
        p["port"] = self.port.value()
        p["username"] = self.username.text()
        p["password"] = self.password.text()
        p["key_path"] = self.key_path.text()
        p["remote_path"] = self.remote_path.text() or "/"
        p["timeout"] = self.timeout.value()
        p["passive_mode"] = p.get("passive_mode", True)
        self._suppress_list = True
        self.profile_list.item(row).setText(
            f"{p['name']}\n{p.get('host', '')}")
        self._suppress_list = False

    def _load_form_from_profile(self, row: int):
        pid = self._pid_at_row(row)
        idx = self._profile_index_by_id(pid) if pid else -1
        if idx < 0:
            return
        p = self._profiles[idx]
        self.profile_name.setText(str(p.get("name", "")))
        self.enabled_cb.setChecked(bool(p.get("enabled", False)))
        self.host.setText(str(p.get("host", "")))
        self.port.setValue(int(p.get("port", 22)))
        self.username.setText(str(p.get("username", "")))
        self.password.setText(str(p.get("password", "")))
        self.key_path.setText(str(p.get("key_path", "")))
        self.remote_path.setText(str(p.get("remote_path", "/")))
        self.timeout.setValue(int(p.get("timeout", 30)))

    def _new_profile(self):
        self._save_form_into_profile_by_row(self.profile_list.currentRow())
        import uuid
        nid = str(uuid.uuid4())
        n = len(self._profiles) + 1
        self._profiles.append({
            "id": nid,
            "name": f"Perfil {n}",
            "enabled": False,
            "host": "",
            "port": 22,
            "username": "",
            "password": "",
            "key_path": "",
            "remote_path": "/",
            "timeout": 30,
            "passive_mode": True,
        })
        self._suppress_list = True
        self._refill_profile_list()
        for i in range(self.profile_list.count()):
            if self._pid_at_row(i) == nid:
                self.profile_list.setCurrentRow(i)
                break
        self._suppress_list = False
        self._prev_row = self.profile_list.currentRow()
        self._load_form_from_profile(self.profile_list.currentRow())

    def _dup_profile(self):
        row = self.profile_list.currentRow()
        if row < 0:
            return
        self._save_form_into_profile_by_row(row)
        import uuid
        pid = self._pid_at_row(row)
        idx = self._profile_index_by_id(pid or "")
        if idx < 0:
            return
        dup = copy.deepcopy(self._profiles[idx])
        dup["id"] = str(uuid.uuid4())
        dup["name"] = str(dup.get("name", "Perfil")) + " (cópia)"
        self._profiles.append(dup)
        self._refill_profile_list()
        for i in range(self.profile_list.count()):
            if self._pid_at_row(i) == dup["id"]:
                self.profile_list.setCurrentRow(i)
                break
        self._prev_row = self.profile_list.currentRow()
        self._load_form_from_profile(self.profile_list.currentRow())

    def _del_profile(self):
        if len(self._profiles) <= 1:
            QMessageBox.information(
                self, "Perfis SFTP", "É necessário manter pelo menos um perfil.")
            return
        row = self.profile_list.currentRow()
        if row < 0:
            return
        pid = self._pid_at_row(row)
        if QMessageBox.question(
                self, "Excluir perfil",
                "Excluir este perfil da lista?\n(A alteração só é gravada ao "
                "clicar em «Salvar e Fechar».)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        idx = self._profile_index_by_id(pid or "")
        if idx >= 0:
            del self._profiles[idx]
        self._refill_profile_list()
        self.profile_list.setCurrentRow(min(row, self.profile_list.count() - 1))
        self._prev_row = self.profile_list.currentRow()
        self._load_form_from_profile(self.profile_list.currentRow())

    def _browse_key(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Chave SSH Privada", "",
            "Chaves SSH (*.pem *.key *.ppk *.rsa);;Todos os arquivos (*)")
        if f:
            self.key_path.setText(f)

    def _test_connection(self):
        row = self.profile_list.currentRow()
        if row >= 0:
            self._save_form_into_profile_by_row(row)
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testando...")
        self.test_result.setText("")
        self.test_result.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        idx = self._profile_index_by_id(self._pid_at_row(self.profile_list.currentRow()) or "")
        p = self._profiles[idx] if idx >= 0 else {}
        cfg = {
            "host": p.get("host", ""),
            "port": int(p.get("port", 22)),
            "username": p.get("username", ""),
            "password": p.get("password", ""),
            "key_path": p.get("key_path", ""),
            "remote_path": p.get("remote_path", "/"),
            "timeout": int(p.get("timeout", 30)),
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
        row = self.profile_list.currentRow()
        if row >= 0:
            self._save_form_into_profile_by_row(row)
        pid = self._pid_at_row(self.profile_list.currentRow()) if row >= 0 else ""
        if not pid and self._profiles:
            pid = str(self._profiles[0].get("id", ""))
        self.cfg.set_sftp_profiles_state(self._profiles, pid)


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
        # Ajusta as cores globais do módulo conforme o tema atual ANTES de criar os widgets
        _apply_settings_theme(self.cfg.get_value("ui", "theme", "dark") != "light")
        self.setWindowTitle("Configurações — SAFX Editor")
        self.setMinimumSize(820, 620)
        self._apply_dialog_style()
        from ui.window_utils import enable_dialog_min_max
        enable_dialog_min_max(self)
        self._build()

    def _apply_dialog_style(self):
        """Aplica o stylesheet do diálogo usando as constantes de tema atuais."""
        self.setStyleSheet(
            f"QDialog{{background:{_DARK};}}"
            f"QTabWidget::pane{{border:1px solid {_BORDER};"
            f"background:{_DARK};border-radius:6px;}}"
            f"QTabBar::tab{{background:{_SURFACE};color:{_MUTED};"
            f"padding:8px 14px;border:none;border-radius:4px 4px 0 0;"
            f"font-size:11px;margin-right:2px;min-width:60px;}}"
            f"QTabBar::tab:selected{{background:{_DARK};color:{_ACCENT};"
            f"font-weight:700;border-bottom:2px solid {_ACCENT};}}"
            f"QTabBar::tab:hover{{color:{_TEXT};}}"
            f"QScrollArea{{border:none;background:{_DARK};}}"
            f"QGroupBox{{border:1px solid {_BORDER};border-radius:6px;"
            f"margin-top:8px;padding-top:4px;color:{_ACCENT};font-weight:600;"
            f"background:{_DARK};}}"
            f"QGroupBox::title{{subcontrol-origin:margin;left:10px;padding:0 4px;"
            f"color:{_ACCENT};}}"
            f"QLabel{{color:{_TEXT};font-size:12px;background:transparent;}}"
            f"QLineEdit{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:4px 8px;color:{_TEXT};font-size:12px;}}"
            f"QLineEdit:focus{{border:1px solid {_ACCENT};}}"
            f"QSpinBox{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:2px 6px;color:{_TEXT};font-size:12px;}}"
            f"QSpinBox:focus{{border:1px solid {_ACCENT};}}"
            f"QSpinBox::up-button,QSpinBox::down-button{{width:18px;"
            f"background:{_BORDER};border:none;}}"
            f"QComboBox{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:2px 8px;color:{_TEXT};font-size:12px;}}"
            f"QComboBox::drop-down{{border:none;width:20px;}}"
            f"QComboBox QAbstractItemView{{background:{_SURFACE};color:{_TEXT};"
            f"border:1px solid {_BORDER};}}"
            f"QCheckBox{{color:{_TEXT};font-size:12px;spacing:6px;}}"
            f"QCheckBox::indicator{{width:16px;height:16px;"
            f"border:1px solid {_BORDER};border-radius:3px;background:{_SURFACE};}}"
            f"QCheckBox::indicator:checked{{background:{_ACCENT};border-color:{_ACCENT};}}"
            f"QTextEdit{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;color:{_TEXT};font-size:12px;padding:4px;}}"
            f"QPlainTextEdit{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:5px;color:{_TEXT};font-size:12px;padding:4px;}}"
            f"QPushButton{{background:{_SURFACE};color:{_TEXT};border:1px solid {_BORDER};"
            f"border-radius:5px;padding:4px 12px;font-size:12px;}}"
            f"QPushButton:hover{{background:{_BORDER};}}"
            f"QPushButton:disabled{{color:{_MUTED};}}")

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
        self.tabs.addTab(self._build_tab_ext_db(), "🗄 Banco (Oracle, Supabase…)")
        self.tabs.addTab(self.tab_sobre, "ℹ Sobre")

        # Permite rolar as abas quando não cabem todas na largura
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)

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
        self._persist_ext_db_tab()
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

    def _resolve_layout_dir_for_settings(self) -> Optional[Path]:
        """Diretório com SAFX*.md (mesma ordem de prioridade do app principal)."""
        cfg_dir = (self.cfg.get_value("general", "layout_dir", "") or "").strip()
        if cfg_dir:
            p = Path(cfg_dir)
            if p.is_dir() and any(p.glob("SAFX*.md")):
                return p
        here = Path(__file__).resolve().parent.parent  # pasta SAFX_Editor
        for c in (
            here / "resources" / "estrutura_md",
            here.parent / "ESTRUTURA" / "estrutura_md",
            here.parent / "MANUAL LAYOUT",
            here / "MANUAL LAYOUT",
        ):
            if c.is_dir() and any(c.glob("SAFX*.md")):
                return c
        return None

    @staticmethod
    def _norm_mandatory(val: Any) -> str:
        t = str(val or "N").strip().upper()
        if t in ("S", "SIM", "Y", "YES", "1", "TRUE"):
            return "S"
        return "N"

    def _fields_from_manual_layout(self, table_name: str) -> List[Dict[str, Any]]:
        """Converte TableLayout (MD) em lista de dicts para a grade."""
        d = self._resolve_layout_dir_for_settings()
        if not d:
            return []
        from core.layout_manager import LayoutManager
        lm = LayoutManager(str(d))
        tl = lm.get_layout(table_name)
        if not tl:
            return []
        out: List[Dict[str, Any]] = []
        for f in tl.fields:
            out.append({
                "name": f.name,
                "type": f.field_type,
                "size": f.size,
                "decimals": f.decimals,
                "mandatory": "S" if f.is_mandatory else "N",
            })
        return out

    def _merge_layout_fields(
            self, base: List[Dict[str, Any]],
            custom: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        base = MANUAL LAYOUT (MD).
        custom = ajustes em custom_layouts: sobrescreve campo pelo nome
        ou acrescenta campos novos ao final.
        """
        if not custom:
            return list(base)
        base_names = {str(b.get("name", "")).strip().upper() for b in base if b.get("name")}
        overrides: Dict[str, Dict[str, Any]] = {}
        extras: List[Dict[str, Any]] = []
        for c in custom:
            nm = str(c.get("name", "")).strip().upper()
            if not nm:
                continue
            row = {
                "name": str(c.get("name", "")).strip(),
                "type": str(c.get("type", "alfa") or "alfa").strip(),
                "size": int(c.get("size", 50) or 50),
                "decimals": int(c.get("decimals", 0) or 0),
                "mandatory": self._norm_mandatory(c.get("mandatory")),
            }
            if nm in base_names:
                overrides[nm] = row
            else:
                extras.append(row)
        merged: List[Dict[str, Any]] = []
        for b in base:
            nm = str(b.get("name", "")).strip().upper()
            merged.append(dict(overrides[nm]) if nm in overrides else dict(b))
        merged.extend(extras)
        return merged

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
            "ℹ  A grade abaixo mostra os campos do MANUAL LAYOUT (arquivos .md).\n"
            "Você pode editar tamanho/tipo/obrigatório ou adicionar campos; ao salvar, "
            "apenas as diferenças ficam em ~/.safx_editor/custom_layouts.json "
            "(o MD original não é alterado).")
        info.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Lista de tabelas SAFX
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Tabelas SAFX:"))
        self._edit_layout_filter = QLineEdit()
        self._edit_layout_filter.setPlaceholderText("Filtrar tabela (ex.: 2013, 07)…")
        self._edit_layout_filter.setClearButtonEnabled(True)
        self._edit_layout_filter.textChanged.connect(self._filter_layout_table_list)
        ll.addWidget(self._edit_layout_filter)
        self._layout_list = QListWidget()
        self._layout_list.setMinimumWidth(160)
        self._layout_list.setMaximumWidth(280)
        layout_dir = self._resolve_layout_dir_for_settings()
        table_names: List[str] = []
        if layout_dir:
            from core.layout_manager import LayoutManager
            table_names = LayoutManager(str(layout_dir)).get_available_tables()
        if not table_names:
            table_names = [f'SAFX{n}' for n in [
                '01', '04', '05', '07', '08', '14', '21', '24', '25', '30', '31',
                '34', '35', '40', '41', '50', '51', '54', '55', '60', '64', '65',
                '71', '75', '82', '83', '92', '93', '96', '97', '108', '109',
                '118', '119', '128', '139', '148', '158', '159', '168', '169',
                '299', '431', '501', '520', '534', '540', '702', '992', '993',
                '2089', '2098', '2099']]
        for t in table_names:
            self._layout_list.addItem(QListWidgetItem(t))
        self._layout_list.currentItemChanged.connect(
            lambda cur, _prev: self._on_layout_table_selected(cur.text() if cur else ''))
        ll.addWidget(self._layout_list, 1)
        splitter.addWidget(left)

        # Editor de campos
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        hdr_fields = QHBoxLayout()
        hdr_fields.setSpacing(8)
        lbl_fields = QLabel("Campos (MANUAL LAYOUT + personalização):")
        lbl_fields.setStyleSheet(f"color:{_TEXT};font-size:12px;font-weight:600;")
        hdr_fields.addWidget(lbl_fields, 1)
        btn_sort_az = QPushButton("A→Z")
        btn_sort_az.setFixedHeight(28)
        btn_sort_az.setToolTip("Ordenar linhas da grade pelo nome do campo (A→Z)")
        btn_sort_az.clicked.connect(lambda: self._layout_sort_fields(1))
        hdr_fields.addWidget(btn_sort_az)
        btn_sort_za = QPushButton("Z→A")
        btn_sort_za.setFixedHeight(28)
        btn_sort_za.setToolTip("Ordenar pelo nome do campo (Z→A)")
        btn_sort_za.clicked.connect(lambda: self._layout_sort_fields(-1))
        hdr_fields.addWidget(btn_sort_za)
        btn_sort_md = QPushButton("Ordem MD")
        btn_sort_md.setFixedHeight(28)
        btn_sort_md.setToolTip("Recarregar campos na ordem original do arquivo .md")
        btn_sort_md.clicked.connect(self._layout_sort_restore_md_order)
        hdr_fields.addWidget(btn_sort_md)
        rl.addLayout(hdr_fields)

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
        splitter.setSizes([200, 600])
        lay.addWidget(splitter, 1)
        if self._layout_list.count() > 0:
            self._layout_list.setCurrentRow(0)
        return w

    def _on_layout_table_selected(self, table_name: str):
        """Carrega campos do MANUAL LAYOUT (.md) e aplica personalização salva."""
        if not table_name:
            return
        self._current_layout_table = table_name
        self._layout_table.setRowCount(0)

        base = self._fields_from_manual_layout(table_name)
        raw_custom = self.cfg.get_value("custom_layouts", table_name, [])
        custom: List[Dict[str, Any]] = raw_custom if isinstance(raw_custom, list) else []
        fields = self._merge_layout_fields(base, custom)

        for field in fields:
            self._layout_add_field_data(field)

        ld = self._resolve_layout_dir_for_settings()
        ld_short = ld.name if ld else "—"
        self._lbl_layout_status.setText(
            f"{table_name}: {len(fields)} campo(s) — MANUAL LAYOUT: {len(base)} "
            f"| ajustes salvos: {len(custom)} | pasta: {ld_short}")

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

    def _filter_layout_table_list(self, text: str):
        if not hasattr(self, '_layout_list'):
            return
        needle = (text or '').strip().lower()
        for i in range(self._layout_list.count()):
            it = self._layout_list.item(i)
            it.setHidden(bool(needle) and needle not in it.text().lower())

    def _layout_sort_fields(self, direction: int):
        """direction: 1 = A→Z, -1 = Z→A (ordem na grade; salvar persiste essa ordem)."""
        tbl = self._layout_table
        if tbl.rowCount() == 0:
            return
        rows: List[Dict[str, Any]] = []
        for r in range(tbl.rowCount()):
            rows.append({
                'name': (tbl.item(r, 0) or _ti('')).text().strip(),
                'type': (tbl.item(r, 1) or _ti('alfa')).text().strip() or 'alfa',
                'size': int((tbl.item(r, 2) or _ti('50')).text() or '50'),
                'decimals': int((tbl.item(r, 3) or _ti('0')).text() or '0'),
                'mandatory': (tbl.item(r, 4) or _ti('N')).text().strip() or 'N',
            })
        rows.sort(key=lambda x: x['name'].upper(), reverse=(direction < 0))
        tbl.setRowCount(0)
        for field in rows:
            self._layout_add_field_data(field)

    def _layout_sort_restore_md_order(self):
        item = self._layout_list.currentItem()
        if not item:
            QMessageBox.information(
                self, "Ordem do layout",
                "Selecione uma tabela na lista à esquerda.")
            return
        self._on_layout_table_selected(item.text())

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
        from PyQt6.QtWidgets import QTableWidget, QHeaderView, QScrollArea, QFrame
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        w = QWidget()
        root_h = QHBoxLayout(w)
        root_h.setContentsMargins(16, 12, 16, 16)
        root_h.setSpacing(14)

        self._ext_profiles = copy.deepcopy(self.cfg.list_ext_db_profiles())
        self._ext_list_block = False
        left_e = QVBoxLayout()
        left_e.addWidget(_label("Perfis de conexão"))
        self.ext_profile_list = QListWidget()
        self.ext_profile_list.setMinimumWidth(200)
        self.ext_profile_list.setMaximumWidth(280)
        self.ext_profile_list.setStyleSheet(
            f"QListWidget{{background:{_SURFACE};border:1px solid {_BORDER};"
            f"border-radius:6px;color:{_TEXT};padding:4px;}}"
            f"QListWidget::item{{padding:8px;border-radius:4px;}}"
            f"QListWidget::item:selected{{background:{_ACCENT};color:{_DARK};}}")
        self._ext_refill_profile_list()
        self.ext_profile_list.currentRowChanged.connect(
            self._on_ext_profile_row_changed)
        left_e.addWidget(self.ext_profile_list)
        row_ex = QHBoxLayout()
        bn = _btn("+ Novo", _SURFACE, _ACCENT, 66)
        bn.clicked.connect(self._ext_new_profile)
        bd = _btn("Duplicar", _SURFACE, _TEXT, 76)
        bd.clicked.connect(self._ext_dup_profile)
        bx = _btn("Excluir", _SURFACE, _RED, 72)
        bx.clicked.connect(self._ext_del_profile)
        row_ex.addWidget(bn)
        row_ex.addWidget(bd)
        row_ex.addWidget(bx)
        left_e.addLayout(row_ex)
        le_tip = QLabel("Vários ambientes ou clientes (ex.: várias bases SFTP/DB).")
        le_tip.setStyleSheet(f"color:{_MUTED};font-size:10px;")
        le_tip.setWordWrap(True)
        left_e.addWidget(le_tip)
        left_e.addStretch()
        root_h.addLayout(left_e, 0)

        col = QVBoxLayout()
        col.setSpacing(14)

        info = QLabel(
            "ℹ  Banco externo OPCIONAL — o sistema funciona normalmente sem ele.\n"
            "Serve para persistir dados, change log e histórico entre sessões "
            "(SQLite, PostgreSQL, Supabase, Oracle, MySQL).\n\n"
            "Importação direta de ERP (SAP RFC, TOTVS REST, Oracle de leitura, etc.) "
            "fica em: menu Arquivo → Importar via ERP / Banco de Dados — não nesta aba.")
        info.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        info.setWordWrap(True)
        col.addWidget(info)

        self.chk_ext_db = QCheckBox("Habilitar banco de dados externo para persistência")
        self.chk_ext_db.setChecked(self.cfg.get_value('ext_db', 'enabled', False))
        self.chk_ext_db.toggled.connect(self._on_ext_db_toggle)
        col.addWidget(self.chk_ext_db)

        gb = QGroupBox("Configuração do Banco")
        gb.setStyleSheet(
            f"QGroupBox{{color:{_ACCENT};font-size:12px;font-weight:700;"
            f"border:1px solid {_BORDER};border-radius:6px;"
            f"margin-top:8px;padding:12px 10px 14px 10px;}}"
            f"QGroupBox::title{{padding:0 6px;}}")
        fl = QFormLayout(gb)
        fl.setSpacing(12)
        fl.setVerticalSpacing(12)
        fl.setHorizontalSpacing(12)
        fl.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        fl.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.edit_ext_profile_name = _line_edit("Ex.: Oracle produção / Cliente X")
        fl.addRow(_label("Nome do perfil:"), self.edit_ext_profile_name)

        self.combo_ext_type = QComboBox()
        for key, name in [('sqlite', 'SQLite (arquivo local)'),
                          ('postgres', 'PostgreSQL'),
                          ('supabase', 'Supabase (PostgreSQL)'),
                          ('oracle', 'Oracle Database'),
                          ('mysql', 'MySQL / MariaDB')]:
            self.combo_ext_type.addItem(name, userData=key)
        self.combo_ext_type.setMinimumHeight(32)
        fl.addRow(_label("Tipo:"), self.combo_ext_type)

        self.edit_ext_host = QLineEdit()
        self.edit_ext_host.setMinimumHeight(30)
        self.edit_ext_host.setPlaceholderText("host ou caminho SQLite")
        fl.addRow(_label("Host/Arquivo:"), self.edit_ext_host)

        self.spin_ext_port = QSpinBox()
        self.spin_ext_port.setRange(0, 65535)
        self.spin_ext_port.setMinimumHeight(30)
        fl.addRow(_label("Porta:"), self.spin_ext_port)

        self.edit_ext_db = QLineEdit()
        self.edit_ext_db.setMinimumHeight(30)
        self.edit_ext_db.setPlaceholderText("database / schema / service_name")
        fl.addRow(_label("Database:"), self.edit_ext_db)

        self.edit_ext_user = QLineEdit()
        self.edit_ext_user.setMinimumHeight(30)
        fl.addRow(_label("Usuário:"), self.edit_ext_user)

        self.edit_ext_pw = QLineEdit()
        self.edit_ext_pw.setMinimumHeight(30)
        self.edit_ext_pw.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addRow(_label("Senha:"), self.edit_ext_pw)

        self.chk_persist_safx = QCheckBox(
            "Salvar tabelas SAFX importadas no banco externo")
        self.chk_persist_safx.setChecked(
            self.cfg.get_value('ext_db', 'persist_tables', False))
        fl.addRow(self.chk_persist_safx)

        self.chk_persist_log = QCheckBox(
            "Salvar change log no banco externo (sempre recomendado)")
        self.chk_persist_log.setChecked(
            self.cfg.get_value('ext_db', 'persist_log', True))
        fl.addRow(self.chk_persist_log)

        col.addWidget(gb)

        gb_scripts = QGroupBox("Scripts de Criação das Tabelas")
        gb_scripts.setStyleSheet(gb.styleSheet())
        sl = QVBoxLayout(gb_scripts)
        sl.setSpacing(10)
        sl.addWidget(QLabel(
            "Baixe o script SQL para criar as tabelas no seu banco antes de conectar:"))

        scripts_row = QHBoxLayout()
        scripts_row.setSpacing(8)
        for db_type, label in [('postgres', 'PostgreSQL/Supabase'),
                                ('oracle', 'Oracle'), ('mysql', 'MySQL'),
                                ('sqlite', 'SQLite')]:
            btn = QPushButton(f"⬇ {label}")
            btn.setMinimumHeight(30)
            btn.clicked.connect(lambda _, t=db_type: self._save_ddl_script(t))
            scripts_row.addWidget(btn)
        sl.addLayout(scripts_row)

        col.addWidget(gb_scripts)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_test = QPushButton("🔌 Testar Conexão")
        btn_test.setMinimumHeight(32)
        btn_test.clicked.connect(self._test_ext_db)
        btn_row.addWidget(btn_test)

        btn_save_ext = QPushButton("💾 Salvar")
        btn_save_ext.setMinimumHeight(32)
        btn_save_ext.setStyleSheet(
            f"QPushButton{{background:#1a4e1a;color:{_GREEN};"
            f"border:1px solid #2a7a2a;border-radius:5px;font-weight:700;}}"
            f"QPushButton:hover{{background:#2a7a2a;color:white;}}")
        btn_save_ext.clicked.connect(self._save_ext_db_settings)
        btn_row.addWidget(btn_save_ext)

        col.addLayout(btn_row)

        self.lbl_ext_db_status = QLabel("")
        self.lbl_ext_db_status.setWordWrap(True)
        col.addWidget(self.lbl_ext_db_status)

        col.addStretch()
        root_h.addLayout(col, 1)

        scroll.setWidget(w)
        outer_lay.addWidget(scroll)
        self._ext_select_active_profile_row()
        self._ext_prev_row = self.ext_profile_list.currentRow()
        return outer

    def _on_ext_db_toggle(self, checked: bool):
        self.cfg.set_value('ext_db', 'enabled', checked)
        row = self.ext_profile_list.currentRow()
        if row >= 0:
            self._ext_save_form_into_row(row)

    def _ext_pid_at_row(self, row: int) -> Optional[str]:
        it = self.ext_profile_list.item(row)
        if not it:
            return None
        return str(it.data(Qt.ItemDataRole.UserRole) or '')

    def _ext_refill_profile_list(self):
        self.ext_profile_list.clear()
        for p in self._ext_profiles:
            pid = str(p.get('id', ''))
            nm = str(p.get('name') or 'Sem nome')
            host = str(p.get('host') or '')
            item = QListWidgetItem(f"{nm}\n{host}")
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self.ext_profile_list.addItem(item)

    def _ext_profile_index_by_id(self, pid: str) -> int:
        for i, p in enumerate(self._ext_profiles):
            if str(p.get('id')) == pid:
                return i
        return -1

    def _ext_save_form_into_row(self, row: int):
        pid = self._ext_pid_at_row(row)
        if not pid:
            return
        idx = self._ext_profile_index_by_id(pid)
        if idx < 0:
            return
        p = self._ext_profiles[idx]
        p['name'] = self.edit_ext_profile_name.text().strip() or p.get('name', 'Perfil')
        p['enabled'] = self.chk_ext_db.isChecked()
        p['type'] = self.combo_ext_type.currentData()
        p['host'] = self.edit_ext_host.text()
        p['port'] = self.spin_ext_port.value()
        p['database'] = self.edit_ext_db.text()
        p['username'] = self.edit_ext_user.text()
        p['password'] = self.edit_ext_pw.text()
        p['persist_tables'] = self.chk_persist_safx.isChecked()
        p['persist_log'] = self.chk_persist_log.isChecked()
        self._ext_list_block = True
        it = self.ext_profile_list.item(row)
        if it:
            it.setText(f"{p['name']}\n{p.get('host', '')}")
        self._ext_list_block = False

    def _ext_load_form_from_row(self, row: int):
        pid = self._ext_pid_at_row(row)
        idx = self._ext_profile_index_by_id(pid or '') if pid else -1
        if idx < 0:
            return
        p = self._ext_profiles[idx]
        self.edit_ext_profile_name.setText(str(p.get('name', '')))
        self.chk_ext_db.setChecked(bool(p.get('enabled', False)))
        db_type = p.get('type', 'sqlite')
        for i in range(self.combo_ext_type.count()):
            if self.combo_ext_type.itemData(i) == db_type:
                self.combo_ext_type.setCurrentIndex(i)
                break
        self.edit_ext_host.setText(str(p.get('host', '')))
        self.spin_ext_port.setValue(int(p.get('port', 5432)))
        self.edit_ext_db.setText(str(p.get('database', '')))
        self.edit_ext_user.setText(str(p.get('username', '')))
        self.edit_ext_pw.setText(str(p.get('password', '')))
        self.chk_persist_safx.setChecked(bool(p.get('persist_tables', False)))
        self.chk_persist_log.setChecked(bool(p.get('persist_log', True)))

    def _on_ext_profile_row_changed(self, row: int):
        if self._ext_list_block or row < 0:
            return
        prev = getattr(self, '_ext_prev_row', -1)
        if prev >= 0 and prev != row:
            self._ext_save_form_into_row(prev)
        self._ext_prev_row = row
        self._ext_load_form_from_row(row)

    def _ext_select_active_profile_row(self):
        aid = self.cfg.get_ext_db_active_profile_id()
        self._ext_list_block = True
        for i in range(self.ext_profile_list.count()):
            if self._ext_pid_at_row(i) == aid:
                self.ext_profile_list.setCurrentRow(i)
                break
        else:
            if self.ext_profile_list.count() > 0:
                self.ext_profile_list.setCurrentRow(0)
        self._ext_list_block = False
        self._ext_load_form_from_row(self.ext_profile_list.currentRow())

    def _ext_new_profile(self):
        import uuid
        self._ext_save_form_into_row(self.ext_profile_list.currentRow())
        from core.config import DEFAULTS
        nid = str(uuid.uuid4())
        ed = dict(DEFAULTS['ext_db'])
        n = len(self._ext_profiles) + 1
        ep: Dict[str, Any] = {'id': nid, 'name': f'Perfil {n}'}
        for k, v in ed.items():
            ep[k] = v
        self._ext_profiles.append(ep)
        self._ext_refill_profile_list()
        self._ext_list_block = True
        for i in range(self.ext_profile_list.count()):
            if self._ext_pid_at_row(i) == nid:
                self.ext_profile_list.setCurrentRow(i)
                break
        self._ext_list_block = False
        self._ext_prev_row = self.ext_profile_list.currentRow()
        self._ext_load_form_from_row(self.ext_profile_list.currentRow())

    def _ext_dup_profile(self):
        import uuid
        row = self.ext_profile_list.currentRow()
        if row < 0:
            return
        self._ext_save_form_into_row(row)
        pid = self._ext_pid_at_row(row)
        idx = self._ext_profile_index_by_id(pid or '')
        if idx < 0:
            return
        dup = copy.deepcopy(self._ext_profiles[idx])
        dup['id'] = str(uuid.uuid4())
        dup['name'] = str(dup.get('name', 'Perfil')) + ' (cópia)'
        self._ext_profiles.append(dup)
        self._ext_refill_profile_list()
        for i in range(self.ext_profile_list.count()):
            if self._ext_pid_at_row(i) == dup['id']:
                self.ext_profile_list.setCurrentRow(i)
                break
        self._ext_prev_row = self.ext_profile_list.currentRow()
        self._ext_load_form_from_row(self.ext_profile_list.currentRow())

    def _ext_del_profile(self):
        if len(self._ext_profiles) <= 1:
            QMessageBox.information(
                self, "Perfis de banco", "Mantenha pelo menos um perfil.")
            return
        row = self.ext_profile_list.currentRow()
        if row < 0:
            return
        if QMessageBox.question(
                self, "Excluir perfil",
                "Excluir este perfil?\n(Só grava em disco em «Salvar» ou "
                "«Salvar e Fechar».)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        pid = self._ext_pid_at_row(row)
        idx = self._ext_profile_index_by_id(pid or '')
        if idx >= 0:
            del self._ext_profiles[idx]
        self._ext_refill_profile_list()
        self.ext_profile_list.setCurrentRow(
            min(row, self.ext_profile_list.count() - 1))
        self._ext_prev_row = self.ext_profile_list.currentRow()
        self._ext_load_form_from_row(self.ext_profile_list.currentRow())

    def _save_ext_db_settings(self):
        row = self.ext_profile_list.currentRow()
        if row >= 0:
            self._ext_save_form_into_row(row)
        pid = self._ext_pid_at_row(self.ext_profile_list.currentRow()) if row >= 0 else ''
        if not pid and self._ext_profiles:
            pid = str(self._ext_profiles[0].get('id', ''))
        self.cfg.set_ext_db_profiles_state(self._ext_profiles, pid)
        self.lbl_ext_db_status.setText("✔ Perfis salvos.")
        self.lbl_ext_db_status.setStyleSheet(f"color:{_GREEN};font-size:11px;")

    def _persist_ext_db_tab(self):
        if not hasattr(self, 'ext_profile_list'):
            return
        row = self.ext_profile_list.currentRow()
        if row >= 0:
            self._ext_save_form_into_row(row)
        pid = self._ext_pid_at_row(row) if row >= 0 else ''
        if not pid and self._ext_profiles:
            pid = str(self._ext_profiles[0].get('id', ''))
        self.cfg.set_ext_db_profiles_state(self._ext_profiles, pid)

    def _test_ext_db(self):
        row = self.ext_profile_list.currentRow()
        if row >= 0:
            self._ext_save_form_into_row(row)
        from core.external_db import ExternalDBManager
        mgr = ExternalDBManager()
        db_type = self.combo_ext_type.currentData()
        host = self.edit_ext_host.text().strip()
        port = self.spin_ext_port.value()
        db_field = self.edit_ext_db.text().strip()
        user = self.edit_ext_user.text().strip()
        password = self.edit_ext_pw.text()

        if db_type == 'sqlite':
            ok, msg = mgr.connect(
                db_type, path=host or 'safx_data.db')
        elif db_type == 'oracle':
            ok, msg = mgr.connect(
                db_type,
                host=host,
                port=port or 1521,
                service_name=db_field,
                user=user,
                password=password,
            )
        elif db_type == 'mysql':
            ok, msg = mgr.connect(
                db_type,
                host=host,
                port=port or 3306,
                database=db_field,
                user=user,
                password=password,
            )
        else:
            # postgres, supabase
            ok, msg = mgr.connect(
                db_type,
                host=host,
                port=port or 5432,
                dbname=db_field,
                user=user,
                password=password,
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
