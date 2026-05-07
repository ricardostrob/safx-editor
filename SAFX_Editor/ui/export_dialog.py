"""
Diálogo de exportação CSV homologado.
- Layout expansível via splitters
- Busca rápida de campos disponíveis
- CSV termina com ; em cada linha
"""
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QComboBox, QListWidget,
                              QListWidgetItem, QFileDialog, QTextEdit,
                              QGroupBox, QMessageBox, QFrame, QSplitter,
                              QWidget, QAbstractItemView, QSizePolicy,
                              QToolButton, QScrollArea, QCheckBox,
                              QRadioButton, QButtonGroup, QLineEdit,
                              QProgressDialog, QApplication)

from core.database import SAFXDatabase, ROW_ID_COL
from core.exporter import SAFXExporter
from core.layout_manager import LayoutManager, DEFAULT_KEY_FIELDS
from core.config import AppConfig

logger = logging.getLogger(__name__)


class FieldListWidget(QListWidget):
    """Lista de campos com drag-and-drop para reordenação."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMinimumWidth(160)
        self.setMinimumHeight(80)
        self.setFont(QFont("Consolas", 11))

    def get_fields(self) -> List[str]:
        return [self.item(i).text() for i in range(self.count())]

    def add_field(self, name: str, color: str = "#cdd6f4", bg: str = ""):
        item = QListWidgetItem(name)
        item.setFont(QFont("Consolas", 11))
        item.setForeground(QColor(color))
        if bg:
            item.setBackground(QColor(bg))
        self.addItem(item)

    def remove_selected(self):
        for item in self.selectedItems():
            self.takeItem(self.row(item))


class ExportDialog(QDialog):
    """Diálogo completo de exportação CSV homologado."""

    def __init__(self, db: SAFXDatabase, exporter: SAFXExporter,
                 layout_manager: LayoutManager,
                 table_name: str,
                 selected_row_ids: Optional[List[int]] = None,
                 all_row_ids: Optional[List[int]] = None,
                 parent=None):
        super().__init__(parent)
        self.db = db
        self.exporter = exporter
        self.layout_manager = layout_manager
        self.table_name = table_name
        self.selected_row_ids = selected_row_ids or []
        self.all_row_ids = all_row_ids or []

        self.layout_def = layout_manager.get_layout(table_name)
        self._all_fields: List[str] = []
        if self.layout_def:
            self._all_fields = self.layout_def.get_field_names()

        # Campos atualmente em "disponíveis" (pode ser filtrado)
        self._avail_all: List[str] = []   # todos sem filtragem

        self.setWindowTitle(f"Exportar {table_name} — Formato Homologado")
        self.setMinimumSize(860, 560)
        self.setSizeGripEnabled(True)

        # Detecta tema ativo
        from core.config import AppConfig
        _cfg = AppConfig.get()
        self._theme = _cfg.get_value("ui", "theme", "dark") or "dark"
        self._is_dark = (self._theme != "light")

        from ui.styles import get_style
        self.setStyleSheet(get_style(self._theme))

        self._splitter_initialized = False   # aplicar tamanhos apenas uma vez
        self._setup_ui()
        self._load_defaults()

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w = min(1100, int(geo.width() * 0.88))
            h = min(820, int(geo.height() * 0.88))
            w = max(w, 860)
            h = max(h, 560)
            self.resize(w, h)
            self.move(
                geo.x() + (geo.width() - w) // 2,
                geo.y() + (geo.height() - h) // 2,
            )
        if not self._splitter_initialized:
            self._splitter_initialized = True
            # Aguarda o layout estar finalizado antes de aplicar tamanhos
            QTimer.singleShot(80, self._apply_splitter_sizes)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # NÃO reseta splitters no resize — deixa o usuário manter sua expansão

    def _apply_splitter_sizes(self):
        """Distribui o espaço dos splitters proporcionalmente — chamado apenas uma vez na abertura."""
        # ── Splitter vertical (Config+Campos | Preview) ──
        if hasattr(self, '_main_splitter'):
            total = self._main_splitter.height()
            if total > 100:
                preview_h = max(150, int(total * 0.30))
                top_h = max(280, total - preview_h)
                self._main_splitter.setSizes([top_h, preview_h])

        # ── Splitter horizontal das colunas de campos ──
        if hasattr(self, '_fields_splitter'):
            total_w = self._fields_splitter.width()
            if total_w > 400:
                btns  = 148          # coluna de botões — tamanho fixo
                avail = max(200, int((total_w - btns) * 0.35))
                rest  = max(140, (total_w - avail - btns) // 2)
                self._fields_splitter.setSizes([avail, btns, rest, rest])

    # ─── UI ───────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Cores do tema ──────────────────────────────────────────────────────
        if self._is_dark:
            H_BG     = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0e1b2e,stop:1 #1a2638)"
            H_BORDER = "#313244"
            H_TITLE  = "#89b4fa"
            H_SUB    = "#6c7086"
            # Modo cards
            CARD_BG      = "#252535"
            CARD_BORDER  = "#45475a"
            CARD_SEL_BG  = "#1e3a5a"
            CARD_SEL_BD  = "#89b4fa"
            CARD_SEL_CLR = "#89b4fa"
            CARD_TXT     = "#a6adc8"
            CARD_HOVER   = "#2a2a42"
            # Destino
            DST_BG       = "#252535"
            DST_BORDER   = "#45475a"
            DST_SEL_BG   = "#1a3a1a"
            DST_SEL_BD   = "#a6e3a1"
            DST_SEL_CLR  = "#a6e3a1"
            DST_TXT      = "#a6adc8"
            DST_HOVER    = "#2a2a42"
        else:
            H_BG     = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1a5ab4,stop:1 #2468c8)"
            H_BORDER = "#b8bcd0"
            H_TITLE  = "#ffffff"
            H_SUB    = "#dce8ff"
            # Modo cards
            CARD_BG      = "#ffffff"
            CARD_BORDER  = "#b8bcd0"
            CARD_SEL_BG  = "#1a5ab4"
            CARD_SEL_BD  = "#1a5ab4"
            CARD_SEL_CLR = "#ffffff"
            CARD_TXT     = "#1a1a2e"
            CARD_HOVER   = "#e8f0fa"
            # Destino
            DST_BG       = "#ffffff"
            DST_BORDER   = "#b8bcd0"
            DST_SEL_BG   = "#e8f8ee"
            DST_SEL_BD   = "#2a8a4a"
            DST_SEL_CLR  = "#1a6a30"
            DST_TXT      = "#1a1a2e"
            DST_HOVER    = "#e8f0fa"

        self._CARD_BG     = CARD_BG
        self._CARD_BORDER = CARD_BORDER
        self._CARD_SEL_BG = CARD_SEL_BG
        self._CARD_SEL_BD = CARD_SEL_BD
        self._CARD_SEL_CLR= CARD_SEL_CLR
        self._CARD_TXT    = CARD_TXT
        self._CARD_HOVER  = CARD_HOVER
        self._DST_BG      = DST_BG
        self._DST_BORDER  = DST_BORDER
        self._DST_SEL_BG  = DST_SEL_BG
        self._DST_SEL_BD  = DST_SEL_BD
        self._DST_SEL_CLR = DST_SEL_CLR
        self._DST_TXT     = DST_TXT
        self._DST_HOVER   = DST_HOVER

        # ══════════════════════════════════════════════════════════════
        # HEADER
        # ══════════════════════════════════════════════════════════════
        header_w = QWidget()
        header_w.setFixedHeight(54)
        header_w.setStyleSheet(
            f"background:{H_BG};border-bottom:2px solid {H_BORDER};")
        h_lay = QHBoxLayout(header_w)
        h_lay.setContentsMargins(20, 0, 20, 0)

        title = QLabel(f"📤  Exportar {self.table_name}")
        title.setStyleSheet(
            f"color:{H_TITLE};font-size:17px;font-weight:800;letter-spacing:0.5px;"
            "background:transparent;")
        h_lay.addWidget(title)
        h_lay.addStretch()

        count_lbl = QLabel(
            f"{len(self.selected_row_ids):,} selecionados  |  "
            f"{len(self.all_row_ids):,} total filtrado")
        count_lbl.setStyleSheet(f"color:{H_SUB};font-size:12px;background:transparent;")
        h_lay.addWidget(count_lbl)

        root.addWidget(header_w)

        # ══════════════════════════════════════════════════════════════
        # SPLITTER PRINCIPAL: [Config + Campos] | [Preview]
        # ══════════════════════════════════════════════════════════════
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setHandleWidth(8)
        main_splitter.setStyleSheet(
            "QSplitter::handle:vertical {"
            "  background:#26263a; border-top:1px solid #45475a;"
            "  border-bottom:1px solid #45475a;"
            "}"
            "QSplitter::handle:vertical:hover { background:#1e3a5a; }")

        # ── Área superior: Config + Campos ──
        top_w = QWidget()
        top_lay = QVBoxLayout(top_w)
        top_lay.setContentsMargins(16, 12, 16, 8)
        top_lay.setSpacing(10)

        # ── Modo de exportação — cards visuais ────────────────────────────────
        mode_group = QGroupBox("Modo de Exportação")
        if self._is_dark:
            mode_group.setStyleSheet(
                "QGroupBox{color:#89b4fa;font-size:12px;font-weight:700;"
                "border:1px solid #313244;border-radius:8px;margin-top:10px;padding:10px 8px 8px 8px;}"
                "QGroupBox::title{padding:0 8px;background:#1e1e2e;}")
        else:
            mode_group.setStyleSheet(
                "QGroupBox{color:#1a5ab4;font-size:12px;font-weight:700;"
                "border:1px solid #b8bcd0;border-radius:8px;margin-top:10px;padding:10px 8px 8px 8px;}"
                "QGroupBox::title{padding:0 8px;background:#f0f2f5;}")

        mode_lay = QHBoxLayout(mode_group)
        mode_lay.setSpacing(10)
        mode_lay.setContentsMargins(4, 4, 4, 4)

        # Cards: usamos QRadioButton mas estilizamos como card
        _MODES = [
            ("rb_mode_homolog",     "📋",  "Homologado",   "TABELA;AÇÃO;CHAVES;ALTERADOS",
             "Formato padrão homologado MasterSAF\n(CSV com separador ;)"),
            ("rb_mode_full",        "📄",  "SAFX Completo","Formato original tab-separado",
             "Exporta todos os campos\nno mesmo formato de importação (TAB)"),
            ("rb_mode_changed_only","✎",  "Só alterados", "Apenas registros modificados",
             "Exporta somente os registros\nalterados nesta sessão (homologado)"),
        ]

        self.rb_mode_homolog = QRadioButton()
        self.rb_mode_full = QRadioButton()
        self.rb_mode_changed_only = QRadioButton()
        _rb_refs = [self.rb_mode_homolog, self.rb_mode_full, self.rb_mode_changed_only]

        _normal_card = (
            f"QRadioButton{{color:{CARD_TXT};font-size:12px;"
            f"background:{CARD_BG};border:2px solid {CARD_BORDER};"
            f"border-radius:8px;padding:10px 14px;min-width:170px;"
            f"font-weight:500;}}"
            f"QRadioButton:hover{{background:{CARD_HOVER};"
            f"border-color:#6c7086;}}"
            f"QRadioButton::indicator{{width:0;height:0;}}")
        _checked_card = (
            f"QRadioButton{{color:{CARD_SEL_CLR};font-size:12px;"
            f"background:{CARD_SEL_BG};border:2px solid {CARD_SEL_BD};"
            f"border-radius:8px;padding:10px 14px;min-width:170px;"
            f"font-weight:700;}}"
            f"QRadioButton::indicator{{width:0;height:0;}}")

        def _update_mode_styles():
            for rb_ in _rb_refs:
                rb_.setStyleSheet(_checked_card if rb_.isChecked() else _normal_card)

        for attr, icon, title_txt, sub_txt, tip in _MODES:
            rb = getattr(self, attr)
            rb.setText(f"{icon}  {title_txt}\n{sub_txt}")
            rb.setToolTip(tip)
            rb.setStyleSheet(_normal_card)
            rb.toggled.connect(_update_mode_styles)
            mode_lay.addWidget(rb)

        mode_lay.addStretch()
        self.rb_mode_homolog.setChecked(True)
        _update_mode_styles()

        self.rb_mode_homolog.toggled.connect(self._on_mode_changed)
        self.rb_mode_full.toggled.connect(self._on_mode_changed)
        self.rb_mode_changed_only.toggled.connect(self._on_mode_changed)

        top_lay.addWidget(mode_group)

        # Linha de configuração: Ação | Escopo | Destino
        config_lay = QHBoxLayout()
        config_lay.setSpacing(12)

        # Estilo para os GroupBoxes internos (tema-aware)
        if self._is_dark:
            _gb_style = (
                "QGroupBox{color:#a6adc8;font-size:11px;font-weight:700;"
                "border:1px solid #313244;border-radius:7px;"
                "margin-top:10px;padding:10px 8px 8px 8px;}"
                "QGroupBox::title{padding:0 6px;background:#1e1e2e;color:#89b4fa;}")
        else:
            _gb_style = (
                "QGroupBox{color:#1a1a2e;font-size:11px;font-weight:700;"
                "border:1px solid #b8bcd0;border-radius:7px;"
                "margin-top:10px;padding:10px 8px 8px 8px;}"
                "QGroupBox::title{padding:0 6px;background:#f0f2f5;color:#1a5ab4;}")

        # Ação
        action_group = QGroupBox("Ação")
        action_group.setStyleSheet(_gb_style)
        action_group.setFixedWidth(130)
        ag_lay = QVBoxLayout(action_group)
        ag_lay.setContentsMargins(8, 8, 8, 8)
        self.combo_action = QComboBox()
        self.combo_action.addItems(["UPDATE", "INSERT", "DELETE"])
        self.combo_action.setFixedHeight(32)
        self.combo_action.setStyleSheet("font-size:13px; font-weight:700;")
        ag_lay.addWidget(self.combo_action)
        ag_lay.addStretch()
        config_lay.addWidget(action_group)

        # Escopo
        scope_group = QGroupBox("Escopo")
        scope_group.setStyleSheet(_gb_style)
        scope_group.setFixedWidth(230)
        sg_lay = QVBoxLayout(scope_group)
        sg_lay.setContentsMargins(8, 8, 8, 8)
        self.radio_selected = QCheckBox(
            f"Apenas selecionados ({len(self.selected_row_ids):,})")
        self.radio_all = QCheckBox(
            f"Todos filtrados ({len(self.all_row_ids):,})")
        self.radio_selected.setChecked(bool(self.selected_row_ids))
        self.radio_all.setChecked(not self.selected_row_ids)
        self.radio_selected.clicked.connect(lambda: self.radio_all.setChecked(False))
        self.radio_all.clicked.connect(lambda: self.radio_selected.setChecked(False))
        sg_lay.addWidget(self.radio_selected)
        sg_lay.addWidget(self.radio_all)
        sg_lay.addStretch()
        config_lay.addWidget(scope_group)

        # Destino — radio cards com indicador visual claro
        dest_group = QGroupBox("Destino")
        dest_group.setStyleSheet(_gb_style)
        dg_lay = QVBoxLayout(dest_group)
        dg_lay.setContentsMargins(6, 8, 6, 6)
        dg_lay.setSpacing(4)

        cfg = AppConfig.get()
        exp_cfg = cfg.export
        sftp_cfg = cfg.sftp
        default_dest = exp_cfg.get("default_destination", "local")

        local_dir_txt  = (exp_cfg.get('local_dir','') or '—')
        local_dir_disp = local_dir_txt[:32] + "…" if len(local_dir_txt) > 32 else local_dir_txt
        srv_dir_txt    = (exp_cfg.get('server_dir','') or '—')
        srv_dir_disp   = srv_dir_txt[:32] + "…" if len(srv_dir_txt) > 32 else srv_dir_txt
        sftp_host      = sftp_cfg.get("host","") if sftp_cfg.get("enabled") else ""

        self.rb_local = QRadioButton("📂  Salvar arquivo (diálogo)")
        self.rb_dir   = QRadioButton(f"📁  Pasta: {local_dir_disp}")
        self.rb_srv   = QRadioButton(f"🖥  Servidor: {srv_dir_disp}")
        self.rb_sftp  = QRadioButton(f"☁  SFTP: {sftp_host or '(não configurado)'}")

        self._dest_group = QButtonGroup(self)
        self._dest_group.addButton(self.rb_local, 0)
        self._dest_group.addButton(self.rb_dir,   1)
        self._dest_group.addButton(self.rb_srv,   2)
        self._dest_group.addButton(self.rb_sftp,  3)

        rb_map = {"local": self.rb_local, "dir": self.rb_dir,
                  "dir_srv": self.rb_srv, "sftp": self.rb_sftp}
        rb_map.get(default_dest, self.rb_local).setChecked(True)

        _dst_normal = (
            f"QRadioButton{{color:{DST_TXT};font-size:12px;padding:5px 10px;"
            f"border-radius:6px;border:1px solid {DST_BORDER};"
            f"background:{DST_BG};font-weight:500;}}"
            f"QRadioButton:hover{{background:{DST_HOVER};"
            f"border-color:#6c7086;}}"
            f"QRadioButton::indicator{{width:13px;height:13px;}}")
        _dst_checked = (
            f"QRadioButton{{color:{DST_SEL_CLR};font-size:12px;padding:5px 10px;"
            f"border-radius:6px;border:2px solid {DST_SEL_BD};"
            f"background:{DST_SEL_BG};font-weight:700;}}"
            f"QRadioButton::indicator{{width:13px;height:13px;}}")

        _dest_rbs = (self.rb_local, self.rb_dir, self.rb_srv, self.rb_sftp)

        def _update_dst_styles():
            for rb_ in _dest_rbs:
                rb_.setStyleSheet(_dst_checked if rb_.isChecked() else _dst_normal)

        # Estilo do botão de engrenagem (tema-aware)
        if self._is_dark:
            _gear_style = (
                "QToolButton{background:#313244;color:#6c7086;border:none;"
                "border-radius:4px;padding:3px 5px;font-size:13px;}"
                "QToolButton:hover{background:#45475a;color:#cdd6f4;}")
        else:
            _gear_style = (
                "QToolButton{background:#dde1ea;color:#6070a0;border:none;"
                "border-radius:4px;padding:3px 5px;font-size:13px;}"
                "QToolButton:hover{background:#b8bcd0;color:#1a1a2e;}")

        def _make_gear_btn(settings_tab: str) -> "QToolButton":
            """Cria botão ⚙ que abre o diálogo de configurações na aba correta."""
            btn = QToolButton()
            btn.setText("⚙")
            btn.setToolTip("Abrir configurações")
            btn.setFixedSize(26, 26)
            btn.setStyleSheet(_gear_style)
            def _open_settings(_checked=False, _tab=settings_tab):
                try:
                    from ui.settings_dialog import SettingsDialog
                    dlg = SettingsDialog(self.parent() or self)
                    # Tenta navegar para a aba correta
                    if hasattr(dlg, 'tabs'):
                        for i in range(dlg.tabs.count()):
                            if _tab.lower() in dlg.tabs.tabText(i).lower():
                                dlg.tabs.setCurrentIndex(i)
                                break
                    dlg.exec()
                except Exception as e:
                    logger.warning(f"Erro ao abrir configurações: {e}")
            btn.clicked.connect(_open_settings)
            return btn

        # Adiciona radio buttons; Servidor e SFTP com botão ⚙
        for i, rb in enumerate(_dest_rbs):
            rb.toggled.connect(_update_dst_styles)
            if i in (2, 3):   # Servidor (2) e SFTP (3) têm engrenagem
                tab_name = "sftp" if i == 3 else "exportação"
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(4)
                row.addWidget(rb, 1)
                row.addWidget(_make_gear_btn(tab_name))
                dg_lay.addLayout(row)
            else:
                dg_lay.addWidget(rb)

        _update_dst_styles()
        dg_lay.addStretch()
        config_lay.addWidget(dest_group)
        config_lay.addStretch()

        top_lay.addLayout(config_lay)

        # ── Separador ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#313244; margin:0;")
        top_lay.addWidget(sep)

        # ── Splitter horizontal: Disponíveis + Botões + [Chaves | Alterados] ──
        fields_splitter = QSplitter(Qt.Orientation.Horizontal)
        fields_splitter.setHandleWidth(6)
        fields_splitter.setStyleSheet(
            "QSplitter::handle:horizontal {"
            "  background:#26263a; border-left:1px solid #45475a;"
            "  border-right:1px solid #45475a;"
            "}"
            "QSplitter::handle:horizontal:hover { background:#1e3a5a; }")

        # ── Coluna 1: Campos Disponíveis + busca ──
        avail_w = QWidget()
        avail_lay = QVBoxLayout(avail_w)
        avail_lay.setContentsMargins(0, 0, 0, 0)
        avail_lay.setSpacing(4)

        avail_header = QWidget()
        avail_header.setStyleSheet(
            "background:#181825; border-radius:6px 6px 0 0; padding:4px;")
        avail_h = QVBoxLayout(avail_header)
        avail_h.setContentsMargins(6, 6, 6, 4)
        avail_h.setSpacing(4)

        lbl_avail = QLabel("📋  Campos Disponíveis")
        lbl_avail.setStyleSheet(
            "color:#89b4fa; font-size:12px; font-weight:700;")
        avail_h.addWidget(lbl_avail)

        # CAMPO DE BUSCA
        self.search_edit = QLineEdit()
        self.search_edit.setFixedHeight(30)
        self.search_edit.setPlaceholderText("🔍 Buscar campo...")
        self.search_edit.setStyleSheet(
            "QLineEdit {"
            "  background:#26263a; color:#cdd6f4; border:1px solid #45475a;"
            "  border-radius:5px; padding:2px 10px; font-size:12px;"
            "}"
            "QLineEdit:focus { border-color:#89b4fa; }")
        self.search_edit.textChanged.connect(self._filter_available)
        avail_h.addWidget(self.search_edit)

        lbl_hint = QLabel("Duplo clique → Chave  |  Selecione + botão → Alterado")
        lbl_hint.setStyleSheet("color:#45475a; font-size:10px;")
        avail_h.addWidget(lbl_hint)

        avail_lay.addWidget(avail_header)

        self.list_avail = QListWidget()
        self.list_avail.setMinimumWidth(200)
        self.list_avail.setMinimumHeight(180)
        self.list_avail.setFont(QFont("Consolas", 11))
        self.list_avail.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_avail.itemDoubleClicked.connect(self._move_to_key)
        self.list_avail.setStyleSheet(
            "QListWidget { background:#13131f; border:1px solid #313244;"
            "  border-radius:0 0 6px 6px; }"
            "QListWidget::item { padding:4px 8px; border-radius:3px; }"
            "QListWidget::item:hover { background:#26263a; }"
            "QListWidget::item:selected { background:#1e3a5a; color:#89b4fa; }")
        avail_lay.addWidget(self.list_avail, 1)

        fields_splitter.addWidget(avail_w)

        # ── Coluna 2: Botões de transferência ──
        arrows_w = QWidget()
        arrows_w.setMinimumWidth(138)
        arrows_w.setMaximumWidth(160)
        arrows_w.setStyleSheet("background:transparent;")
        arrows_lay = QVBoxLayout(arrows_w)
        arrows_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrows_lay.setSpacing(6)
        arrows_lay.setContentsMargins(4, 8, 4, 8)

        arrows_lay.addStretch()

        def _arrow_btn(text: str, tooltip: str, color_bg: str,
                        color_fg: str) -> QPushButton:
            b = QPushButton(text)
            b.setMinimumHeight(32)
            b.setMinimumWidth(124)
            b.setMaximumWidth(152)
            b.setToolTip(tooltip)
            b.setStyleSheet(
                f"QPushButton{{background:{color_bg};color:{color_fg};"
                f"border:none;border-radius:6px;font-size:11px;"
                f"font-weight:700;padding:4px 8px;}}"
                f"QPushButton:hover{{opacity:0.85;}}"
                f"QPushButton:pressed{{padding-top:6px;}}")
            return b

        self.btn_to_key = _arrow_btn(
            "→ Campo Chave",
            "Mover selecionados para campos chave (identifica o registro)",
            "#2a1a3e", "#cba6f7")
        self.btn_to_key.clicked.connect(self._move_to_key)
        arrows_lay.addWidget(self.btn_to_key)

        self.btn_to_change = _arrow_btn(
            "→ Alterado",
            "Mover selecionados para campos alterados (valores novos)",
            "#1a2e1a", "#a6e3a1")
        self.btn_to_change.clicked.connect(self._move_to_change)
        arrows_lay.addWidget(self.btn_to_change)

        arrows_lay.addSpacing(8)

        self.btn_remove = _arrow_btn(
            "← Devolver",
            "Devolver campo selecionado para a lista de disponíveis",
            "#2a1a1a", "#f38ba8")
        self.btn_remove.clicked.connect(self._remove_from_lists)
        arrows_lay.addWidget(self.btn_remove)

        arrows_lay.addSpacing(8)

        self.btn_reset = _arrow_btn(
            "↺ Redefinir",
            "Restaurar configuração padrão de campos",
            "#252535", "#6c7086")
        self.btn_reset.clicked.connect(self._load_defaults)
        arrows_lay.addWidget(self.btn_reset)

        arrows_lay.addStretch()
        fields_splitter.addWidget(arrows_w)

        # ── Coluna 3: Campos Chave ──
        key_w = QWidget()
        key_lay = QVBoxLayout(key_w)
        key_lay.setContentsMargins(0, 0, 0, 0)
        key_lay.setSpacing(4)

        key_lbl = QLabel("🔑  Campos Chave  (identificação do registro)")
        key_lbl.setStyleSheet(
            "color:#cba6f7; font-size:12px; font-weight:700;"
            "background:#2a1a3e; padding:6px 10px; border-radius:6px 6px 0 0;")
        key_lay.addWidget(key_lbl)

        lbl_key_hint = QLabel("Identifica unicamente cada registro na tabela")
        lbl_key_hint.setStyleSheet("color:#45475a; font-size:10px; padding:0 6px;")
        key_lay.addWidget(lbl_key_hint)

        self.list_keys = FieldListWidget()
        self.list_keys.itemDoubleClicked.connect(self._remove_key)
        self.list_keys.setStyleSheet(
            "QListWidget { background:#13131f; border:1px solid #3a1a5e;"
            "  border-radius:0 0 6px 6px; }"
            "QListWidget::item { padding:4px 8px; border-radius:3px; }"
            "QListWidget::item:hover { background:#2a1a3e; }"
            "QListWidget::item:selected { background:#3a1a5e; color:#cba6f7; }")
        key_lay.addWidget(self.list_keys, 1)

        fields_splitter.addWidget(key_w)

        # ── Coluna 4: Campos Alterados ──
        chg_w = QWidget()
        chg_lay = QVBoxLayout(chg_w)
        chg_lay.setContentsMargins(0, 0, 0, 0)
        chg_lay.setSpacing(4)

        chg_lbl = QLabel("✎  Campos Alterados  (valores novos a exportar)")
        chg_lbl.setStyleSheet(
            "color:#a6e3a1; font-size:12px; font-weight:700;"
            "background:#1a2e1a; padding:6px 10px; border-radius:6px 6px 0 0;")
        chg_lay.addWidget(chg_lbl)

        lbl_chg_hint = QLabel("Campos cujos valores novos serão exportados")
        lbl_chg_hint.setStyleSheet("color:#45475a; font-size:10px; padding:0 6px;")
        chg_lay.addWidget(lbl_chg_hint)

        self.list_changes = FieldListWidget()
        self.list_changes.itemDoubleClicked.connect(self._remove_change)
        self.list_changes.setStyleSheet(
            "QListWidget { background:#13131f; border:1px solid #1a4e1a;"
            "  border-radius:0 0 6px 6px; }"
            "QListWidget::item { padding:4px 8px; border-radius:3px; }"
            "QListWidget::item:hover { background:#1a2e1a; }"
            "QListWidget::item:selected { background:#1a4e1a; color:#a6e3a1; }")
        chg_lay.addWidget(self.list_changes, 1)

        fields_splitter.addWidget(chg_w)

        # Salva referência — proporções aplicadas no showEvent após resize
        self._fields_splitter = fields_splitter

        top_lay.addWidget(fields_splitter, 1)

        main_splitter.addWidget(top_w)

        # ── Área inferior: Preview ──
        preview_w = QWidget()
        prev_lay = QVBoxLayout(preview_w)
        prev_lay.setContentsMargins(16, 8, 16, 8)
        prev_lay.setSpacing(6)

        prev_toolbar = QHBoxLayout()

        lbl_prev = QLabel("🔍  Preview do CSV  —  mostra primeiras 10 linhas")
        lbl_prev.setStyleSheet(
            "color:#89b4fa; font-size:12px; font-weight:700;")
        prev_toolbar.addWidget(lbl_prev)

        self.btn_preview = QPushButton("▶  Gerar Preview")
        self.btn_preview.setFixedHeight(30)
        self.btn_preview.setFixedWidth(140)
        self.btn_preview.setStyleSheet(
            "QPushButton{background:#1e4a8a;color:#89b4fa;border:none;"
            "border-radius:5px;font-size:12px;font-weight:700;}"
            "QPushButton:hover{background:#2a5fa0;color:white;}")
        self.btn_preview.clicked.connect(self._generate_preview)
        prev_toolbar.addWidget(self.btn_preview)

        prev_toolbar.addStretch()

        self.lbl_preview_info = QLabel("")
        self.lbl_preview_info.setStyleSheet("color:#6c7086; font-size:11px;")
        prev_toolbar.addWidget(self.lbl_preview_info)

        prev_lay.addLayout(prev_toolbar)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(QFont("Consolas", 10))
        self.preview_text.setStyleSheet(
            "QTextEdit { background:#0d0d1a; color:#a6e3a1;"
            "  border:1px solid #313244; border-radius:4px;"
            "  padding:6px; line-height:1.4; }")
        prev_lay.addWidget(self.preview_text, 1)

        lbl_format = QLabel(
            "ℹ  Formato: TABELA;ACAO;[CAMPOS_CHAVE...];[CAMPOS_ALTERADOS...];  "
            "(cada linha termina com ;  |  encoding: latin-1  |  separador: ;  |  MS-DOS \\r\\n)")
        lbl_format.setStyleSheet("color:#45475a; font-size:10px; font-style:italic;")
        prev_lay.addWidget(lbl_format)

        main_splitter.addWidget(preview_w)
        # Splitter sem setSizes fixo — o showEvent aplica após o resize
        self._main_splitter = main_splitter

        root.addWidget(main_splitter, 1)

        # ══════════════════════════════════════════════════════════════
        # BARRA DE BOTÕES FINAIS — sempre visível, nunca comprimida
        # ══════════════════════════════════════════════════════════════
        btn_bar = QWidget()
        btn_bar.setFixedHeight(54)
        btn_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_bar.setStyleSheet(
            "background:#181825; border-top:2px solid #313244;")
        b_lay = QHBoxLayout(btn_bar)
        b_lay.setContentsMargins(16, 8, 16, 8)
        b_lay.setSpacing(8)

        b_lay.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setFixedWidth(100)
        self.btn_cancel.clicked.connect(self.reject)
        b_lay.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("💾  Exportar CSV Homologado")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setMinimumWidth(220)
        self.btn_export.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "    stop:0 #1e6ab4, stop:1 #1450a0);"
            "  color: white; border: none; border-radius: 6px;"
            "  font-size: 13px; font-weight: 800; padding: 0 16px;"
            "}"
            "QPushButton:hover { background: #2a7ac8; }"
            "QPushButton:pressed { padding-top: 3px; }")
        self.btn_export.clicked.connect(self._do_export)
        b_lay.addWidget(self.btn_export)

        root.addWidget(btn_bar)

    # ─── Dados ────────────────────────────────────────────────────────────────

    def _load_defaults(self):
        """Carrega configuração padrão de campos chave.
        Auto-preenche campos alterados com base no change log da sessão."""
        self.search_edit.clear()
        self.list_avail.clear()
        self.list_keys.clear()
        self.list_changes.clear()

        default_keys = DEFAULT_KEY_FIELDS.get(self.table_name, [])

        # Detecta campos que foram alterados nesta sessão (change log)
        changed_in_session = []
        seen_changed = set()
        for entry in self.db.get_change_log():
            if entry.get('table') == self.table_name:
                field = entry.get('field', '')
                if (field and field in self._all_fields
                        and field not in seen_changed
                        and field not in default_keys):
                    changed_in_session.append(field)
                    seen_changed.add(field)

        placed = set(default_keys) | set(changed_in_session)

        # Campos chave padrão
        for fname in default_keys:
            if fname in self._all_fields:
                self.list_keys.add_field(fname, color="#cba6f7", bg="#2a1a3e")

        # Campos alterados na sessão — auto-preenchidos
        for fname in changed_in_session:
            self.list_changes.add_field(fname, color="#a6e3a1")

        # Restantes → disponíveis
        self._avail_all = [f for f in self._all_fields if f not in placed]
        for fname in self._avail_all:
            item = QListWidgetItem(fname)
            item.setFont(QFont("Consolas", 11))
            self.list_avail.addItem(item)

        # Hint sobre campos auto-detectados
        if changed_in_session:
            self.lbl_preview_info.setText(
                f"✔ {len(changed_in_session)} campo(s) alterado(s) nesta sessão "
                f"foram pré-selecionados automaticamente")

    def _filter_available(self, text: str):
        """Filtra a lista de campos disponíveis em tempo real."""
        text = text.lower().strip()
        for i in range(self.list_avail.count()):
            item = self.list_avail.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    # ─── Movimentos de campo ──────────────────────────────────────────────────

    def _move_to_key(self):
        for item in self.list_avail.selectedItems():
            name = item.text()
            self.list_avail.takeItem(self.list_avail.row(item))
            self._avail_all = [f for f in self._avail_all if f != name]
            self.list_keys.add_field(name, color="#cba6f7", bg="#2a1a3e")

    def _move_to_change(self):
        for item in self.list_avail.selectedItems():
            name = item.text()
            self.list_avail.takeItem(self.list_avail.row(item))
            self._avail_all = [f for f in self._avail_all if f != name]
            self.list_changes.add_field(name, color="#a6e3a1")

    def _remove_key(self, item: QListWidgetItem):
        name = item.text()
        self.list_keys.takeItem(self.list_keys.row(item))
        self._add_to_avail(name)

    def _remove_change(self, item: QListWidgetItem):
        name = item.text()
        self.list_changes.takeItem(self.list_changes.row(item))
        self._add_to_avail(name)

    def _remove_from_lists(self):
        for item in list(self.list_keys.selectedItems()):
            name = item.text()
            self.list_keys.takeItem(self.list_keys.row(item))
            self._add_to_avail(name)
        for item in list(self.list_changes.selectedItems()):
            name = item.text()
            self.list_changes.takeItem(self.list_changes.row(item))
            self._add_to_avail(name)

    def _add_to_avail(self, name: str):
        # Verifica se já existe na lista
        for i in range(self.list_avail.count()):
            if self.list_avail.item(i).text() == name:
                return
        self._avail_all.append(name)
        item = QListWidgetItem(name)
        item.setFont(QFont("Consolas", 11))
        # Aplica filtro de busca atual
        txt = self.search_edit.text().lower().strip()
        if txt and txt not in name.lower():
            item.setHidden(True)
        self.list_avail.addItem(item)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _get_key_fields(self) -> List[str]:
        return self.list_keys.get_fields()

    def _get_change_fields(self) -> List[str]:
        return self.list_changes.get_fields()

    def _get_row_ids(self) -> List[int]:
        if self.radio_selected.isChecked() and self.selected_row_ids:
            return self.selected_row_ids
        return self.all_row_ids

    def _get_rows_data(self, row_ids: List[int]):
        if not row_ids:
            return [], []
        return self.db.get_rows_by_ids(self.table_name, row_ids)

    # ─── Preview ──────────────────────────────────────────────────────────────

    def _on_mode_changed(self):
        """Ajusta visibilidade dos painéis de campos conforme o modo."""
        is_full = self.rb_mode_full.isChecked()
        # No modo SAFX completo, não precisamos de campos chave/alterados
        if hasattr(self, 'list_keys'):
            for w in (self.list_keys, self.list_changes,
                      self.btn_to_key, self.btn_to_change,
                      self.btn_remove, self.btn_reset,
                      self.list_avail, self.search_edit):
                try:
                    w.setEnabled(not is_full)
                    w.setStyleSheet(
                        w.styleSheet() +
                        ("opacity:0.4;" if is_full else ""))
                except Exception:
                    pass
        # Ajusta título do botão de exportar
        if is_full:
            self.btn_export.setText("📄  Exportar SAFX (formato original)")
        elif self.rb_mode_changed_only.isChecked():
            self.btn_export.setText("✎  Exportar Somente Alterados")
        else:
            self.btn_export.setText("💾  Exportar CSV Homologado")

    def _generate_preview(self):
        row_ids = self._get_row_ids()

        # Modo SAFX completo
        if self.rb_mode_full.isChecked():
            cols, rows = self._get_rows_data(row_ids[:10])
            if not rows:
                self.preview_text.setText("Nenhum dado para exportar.")
                return
            preview_str = self.exporter.preview_full_safx(
                self.table_name, cols, rows, max_preview=5)
            self.preview_text.setText(preview_str)
            self.lbl_preview_info.setText(
                f"Preview SAFX completo — {len(row_ids):,} linha(s)  "
                f"| {len(cols)-1} campo(s)  (tab-separado)")
            return

        # Modo homologado (normal ou só alterados)
        key_fields = self._get_key_fields()
        change_fields = self._get_change_fields()
        action = self.combo_action.currentText()

        if not key_fields:
            self.preview_text.setText("⚠ Selecione pelo menos um campo chave.")
            return
        if not change_fields:
            self.preview_text.setText("⚠ Selecione pelo menos um campo alterado.")
            return

        # Modo "apenas alterados": filtra pelos row_ids do change log
        if self.rb_mode_changed_only.isChecked():
            changed_ids = self._get_changed_row_ids()
            if not changed_ids:
                self.preview_text.setText(
                    "⚠ Nenhum registro alterado nesta sessão.\n"
                    "Use o modo Homologado completo para exportar todos os registros.")
                return
            row_ids = changed_ids

        cols, rows = self._get_rows_data(row_ids[:20])
        if not rows:
            self.preview_text.setText("Nenhum dado para exportar.")
            return

        preview_str = self.exporter.preview(
            self.table_name, action, key_fields, change_fields,
            cols, rows, max_preview=10)

        self.preview_text.setText(preview_str)
        self.lbl_preview_info.setText(
            f"Preview de {min(10, len(rows))} de {len(row_ids):,} linha(s)")

    # ─── Exportação ───────────────────────────────────────────────────────────

    def _get_changed_row_ids(self) -> List[int]:
        """Retorna row_ids de registros que foram alterados no change log."""
        seen = set()
        result = []
        for entry in self.db.get_change_log():
            if entry.get('table') == self.table_name:
                rid = entry.get('row_id')
                if rid is not None and rid not in seen:
                    seen.add(rid)
                    result.append(rid)
        return result

    def _do_export(self):
        row_ids = self._get_row_ids()
        action = self.combo_action.currentText()
        is_full_mode = self.rb_mode_full.isChecked()
        is_changed_only = self.rb_mode_changed_only.isChecked()

        # Modo SAFX completo — não precisa de campos chave/alterados
        if not is_full_mode:
            key_fields = self._get_key_fields()
            change_fields = self._get_change_fields()
            if not key_fields:
                QMessageBox.warning(self, "Atenção",
                                    "Selecione pelo menos um campo chave.")
                return
            if not change_fields:
                QMessageBox.warning(self, "Atenção",
                                    "Selecione pelo menos um campo alterado.")
                return
        else:
            key_fields = []
            change_fields = []

        # Modo apenas alterados — restringe row_ids
        if is_changed_only:
            row_ids = self._get_changed_row_ids()
            if not row_ids:
                QMessageBox.warning(self, "Atenção",
                                    "Nenhum registro alterado nesta sessão para exportar.")
                return

        if not row_ids:
            QMessageBox.warning(self, "Atenção", "Nenhuma linha para exportar.")
            return

        dest_id = self._dest_group.checkedId()
        cfg = AppConfig.get()
        exp_cfg = cfg.export
        if is_full_mode:
            default_name = f"{self.table_name}_completo.txt"
            save_filter = "TXT Files (*.txt);;Todos os arquivos (*)"
            save_title = "Salvar SAFX Completo"
        else:
            default_name = f"{self.table_name}_{action}.csv"
            save_filter = "CSV Files (*.csv);;Todos os arquivos (*)"
            save_title = "Salvar CSV Homologado"

        if dest_id == 0:
            path, _ = QFileDialog.getSaveFileName(
                self, save_title,
                str(Path(exp_cfg.get("local_dir", "")) / default_name),
                save_filter)
            if not path:
                return

        elif dest_id == 1:
            local_dir = exp_cfg.get("local_dir", "")
            if not local_dir:
                QMessageBox.warning(self, "Pasta não configurada",
                                    "Configure em: Arquivo > Configurações > Exportação")
                return
            os.makedirs(local_dir, exist_ok=True)
            path = str(Path(local_dir) / default_name)

        elif dest_id == 2:
            server_dir = exp_cfg.get("server_dir", "")
            if not server_dir:
                QMessageBox.warning(self, "Pasta não configurada",
                                    "Configure em: Arquivo > Configurações > Exportação")
                return
            try:
                os.makedirs(server_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Erro de acesso",
                                     f"Não foi possível acessar:\n{server_dir}\n\n{e}")
                return
            path = str(Path(server_dir) / default_name)

        elif dest_id == 3:
            sftp_cfg = cfg.sftp
            if not sftp_cfg.get("host"):
                QMessageBox.warning(self, "SFTP não configurado",
                                    "Configure em: Arquivo > Configurações > SFTP")
                return
            import tempfile
            path = tempfile.mktemp(suffix=f"_{default_name}")

        else:
            return

        # Gera o arquivo
        cols, rows = self._get_rows_data(row_ids)
        if not rows:
            QMessageBox.warning(self, "Atenção", "Nenhum dado encontrado.")
            return

        if is_full_mode:
            # Modo SAFX completo: formato original tab-separado
            default_name = f"{self.table_name}_completo.txt"
            count, msg = self.exporter.export_full_safx(
                self.table_name, cols, rows, path)
        else:
            count, msg = self.exporter.export(
                self.table_name, action, key_fields, change_fields,
                cols, rows, path)

        if count <= 0:
            QMessageBox.critical(self, "Erro na Exportação", msg)
            return

        # SFTP upload
        if dest_id == 3:
            sftp_cfg = cfg.sftp
            from core.sftp_manager import SFTPManager

            progress = QProgressDialog(
                f"Enviando {default_name} via SFTP...", "Cancelar",
                0, 100, self)
            progress.setWindowTitle("Upload SFTP")
            progress.setModal(True)
            progress.setValue(0)
            QApplication.processEvents()

            mgr = SFTPManager.from_config(sftp_cfg)

            def _sftp_progress(transferred: int, total: int):
                if total > 0:
                    progress.setValue(int(100 * transferred / total))
                    QApplication.processEvents()

            ok_sftp, sftp_msg = mgr.upload_file(path, default_name, _sftp_progress)
            progress.close()
            try:
                os.remove(path)
            except Exception:
                pass

            if ok_sftp:
                QMessageBox.information(self, "Concluído",
                                        f"{msg}\n\n{sftp_msg}")
                self.accept()
            else:
                QMessageBox.critical(self, "Erro SFTP",
                                     f"Arquivo gerado mas upload falhou:\n\n{sftp_msg}")
            return

        # Sucesso local
        if exp_cfg.get("open_after_export", False):
            import subprocess, sys
            folder = str(Path(path).parent)
            if sys.platform == "win32":
                subprocess.Popen(f'explorer "{folder}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])

        QMessageBox.information(
            self, "Exportação Concluída",
            f"{msg}\n\nDestino: {path}")
        self.accept()
