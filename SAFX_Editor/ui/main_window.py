"""
Janela principal do SAFX Editor.
"""
import os
import sys
import logging
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap, QAction, QKeySequence
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QSplitter, QTabWidget, QListWidget, QListWidgetItem,
                              QLabel, QPushButton, QFileDialog, QDialog,
                              QProgressDialog, QMessageBox, QStatusBar,
                              QToolBar, QFrame, QComboBox, QApplication,
                              QMenuBar, QMenu, QGroupBox, QProgressBar,
                              QSizePolicy, QScrollArea, QInputDialog)

from core.database import SAFXDatabase, ROW_ID_COL
from core.layout_manager import LayoutManager, DEFAULT_KEY_FIELDS
from core.safx_parser import SAFXParser
from core.exporter import SAFXExporter
from core.config import AppConfig
from core.api_server import APIServer
from ui.data_panel import DataPanel
from ui.sql_panel import SQLPanel
from ui.export_dialog import ExportDialog
from ui.settings_dialog import SettingsDialog
from ui.change_report_dialog import ChangeReportDialog
from ui.styles import MAIN_STYLE

logger = logging.getLogger(__name__)

# ── Caminho padrão do MANUAL LAYOUT ──
# Relativo ao script: ../MANUAL LAYOUT
_THIS_DIR = Path(__file__).parent
_DEFAULT_LAYOUT_DIR = _THIS_DIR.parent.parent / "MANUAL LAYOUT"


class ImportWorker(QThread):
    """
    Thread de importação com suporte a arquivos de MILHÕES de linhas.
    Usa estratégia chunked: lê e insere em lotes para não estourar memória.
    """
    progress = pyqtSignal(int, str)   # percentual (0-100), mensagem
    finished = pyqtSignal(str, int)   # table_name, total_count
    error = pyqtSignal(str)

    CHUNK_SIZE = 50_000   # linhas por lote (balanceio memória x velocidade)

    def __init__(self, parser: SAFXParser, db: SAFXDatabase,
                 filepath: str, table_name: str):
        super().__init__()
        self.parser = parser
        self.db = db
        self.filepath = filepath
        self.table_name = table_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress.emit(2, f"Verificando layout de {self.table_name}...")

            layout = self.parser.layout_manager.get_layout(self.table_name)
            if not layout:
                self.error.emit(f"Layout não encontrado para: {self.table_name}")
                return

            # Conta linhas do arquivo para calcular progresso
            self.progress.emit(4, "Contando linhas do arquivo...")
            total_lines = self.parser.count_lines(self.filepath)
            self.progress.emit(6, f"Total de linhas: {total_lines:,}")

            field_names = layout.get_field_names()
            total_inserted = 0
            first_chunk = True

            # Leitura chunked
            chunk: list = []
            with open(self.filepath, 'r', encoding='latin-1', errors='replace') as f:
                for line_num, raw_line in enumerate(f):
                    if self._cancelled:
                        self.error.emit("Importação cancelada pelo usuário.")
                        return

                    line = raw_line.rstrip('\n\r')
                    if not line.strip():
                        continue

                    parts = line.split('\t')
                    record = {
                        fname: (self.parser._clean(parts[i]) if i < len(parts) else '')
                        for i, fname in enumerate(field_names)
                    }
                    chunk.append(record)

                    if len(chunk) >= self.CHUNK_SIZE:
                        if first_chunk:
                            # Primeiro chunk: cria tabela e carrega
                            count = self.db.load_table(self.table_name, layout, chunk)
                            first_chunk = False
                        else:
                            # Chunks seguintes: apenas insere
                            count = self.db.append_to_table(self.table_name, chunk)

                        total_inserted += count
                        chunk = []

                        # Progresso: 6% → 98%
                        if total_lines > 0:
                            pct = 6 + int(92 * line_num / total_lines)
                        else:
                            pct = 50
                        self.progress.emit(
                            min(pct, 97),
                            f"Inserindo... {total_inserted:,} de ~{total_lines:,} linhas"
                        )

            # Chunk final
            if chunk:
                if first_chunk:
                    count = self.db.load_table(self.table_name, layout, chunk)
                else:
                    count = self.db.append_to_table(self.table_name, chunk)
                total_inserted += count

            self.progress.emit(100, f"Concluido! {total_inserted:,} registros")
            self.finished.emit(self.table_name, total_inserted)

        except Exception as e:
            logger.error(f"Erro na importacao: {e}", exc_info=True)
            self.error.emit(str(e))


class TableSidebarItem(QListWidgetItem):
    """Item da sidebar com info da tabela."""

    def __init__(self, table_name: str, row_count: int = 0,
                 is_external: bool = False):
        super().__init__()
        self.table_name = table_name
        self.row_count = row_count
        self.is_external = is_external
        self._update_text()
        self.setFont(QFont("Segoe UI", 11))

    def _update_text(self):
        if self.is_external:
            self.setText(
                f"📊 {self.table_name}\n   {self.row_count:,} registros (externa)")
        else:
            self.setText(f"  {self.table_name}\n  {self.row_count:,} registros")

    def update_count(self, count: int):
        self.row_count = count
        self._update_text()


class MainWindow(QMainWindow):
    """Janela principal do SAFX Editor."""

    def __init__(self, layout_dir: Optional[str] = None):
        super().__init__()
        self.cfg = AppConfig.get()

        # Carrega layout dir da config se não informado
        cfg_layout = self.cfg.get_value("general", "layout_dir", "")
        self._layout_dir = layout_dir or cfg_layout or str(_DEFAULT_LAYOUT_DIR)
        self._current_table: Optional[str] = None
        self._key_fields: dict = dict(DEFAULT_KEY_FIELDS)
        self._import_workers: List[ImportWorker] = []

        # Inicializa camada de dados
        self.db = SAFXDatabase()
        self.layout_manager = LayoutManager(self._layout_dir)
        self.parser = SAFXParser(self.layout_manager)
        self.exporter = SAFXExporter(self.layout_manager)

        # API Server
        self._api_server: Optional[APIServer] = None

        self._setup_window()
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._apply_style()
        self._update_ui_state()

        # Inicia API se configurada
        if self.cfg.get_value("api", "enabled", False):
            self._start_api_server()

    def _setup_window(self):
        self.setWindowTitle("SAFX Editor — MasterSAF Data Adjuster | Adejo Desenvolvimento")
        self.setMinimumSize(900, 560)

        # Determina tamanho/posição com base na resolução disponível
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            saved_w = self.cfg.get_value("window", "width", 0)
            saved_h = self.cfg.get_value("window", "height", 0)
            was_max = self.cfg.get_value("window", "maximized", False)

            if was_max:
                self.showMaximized()
                return

            # Se não há valor salvo, usa 90% da tela disponível
            w = saved_w if saved_w > 1100 else int(geo.width() * 0.90)
            h = saved_h if saved_h > 650 else int(geo.height() * 0.90)

            self.resize(w, h)
            self.move(
                geo.x() + (geo.width() - w) // 2,
                geo.y() + (geo.height() - h) // 2,
            )
        else:
            w = self.cfg.get_value("window", "width", 1400)
            h = self.cfg.get_value("window", "height", 850)
            self.resize(w, h)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Splitter principal ──
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(8)
        self.main_splitter.setOpaqueResize(True)

        # ── Sidebar ──
        sidebar = self._create_sidebar()
        self.main_splitter.addWidget(sidebar)

        # ── Área principal ──
        main_area = self._create_main_area()
        self.main_splitter.addWidget(main_area)

        self.main_splitter.setSizes([240, 1160])
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)

        main_layout.addWidget(self.main_splitter)

        # ── Status bar ──
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Pronto — Importe um arquivo SAFX para começar")

        # Indicador API
        self.lbl_api_status = QLabel("● API OFF")
        self.lbl_api_status.setStyleSheet(
            "color:#45475a; font-size:11px; padding:0 8px; font-weight:600;")
        self.status_bar.addPermanentWidget(self.lbl_api_status)

        # Label de layout dir
        self.lbl_layout_dir = QLabel()
        self.lbl_layout_dir.setStyleSheet("color:#6c7086; font-size:11px; padding:0 8px;")
        self._update_layout_dir_label()
        self.status_bar.addPermanentWidget(self.lbl_layout_dir)

        # Rodapé de copyright (canto direito da status bar)
        from core.about import DEVELOPER_COMPANY, APP_VERSION
        lbl_copy = QLabel(f"  {DEVELOPER_COMPANY}  •  v{APP_VERSION}  ")
        lbl_copy.setStyleSheet(
            "color:#45475a; font-size:10px; padding:0 6px;"
            "border-left:1px solid #313244;")
        self.status_bar.addPermanentWidget(lbl_copy)

        # QMainWindow: permite docks aninhados e animação (base para UI adaptativa)
        self.setDockNestingEnabled(True)
        self.setAnimated(True)

    def _create_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet("#sidebar { background:#181825; border-right:1px solid #313244; }")
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(280)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header com logo Adejo
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet("background:#0e1b2e; border-bottom:2px solid #1a3055;")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 4)
        h_layout.setSpacing(2)

        # Logo
        logo_path = str(Path(__file__).parent.parent / "assets" / "adejo_logo.png")
        if Path(logo_path).exists() and self.cfg.get_value("branding", "show_logo", True):
            logo_lbl = QLabel()
            pix = QPixmap(logo_path).scaled(
                110, 40, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
            h_layout.addWidget(logo_lbl)
        else:
            lbl_brand = QLabel("ADEJO")
            lbl_brand.setStyleSheet(
                "color:white; font-size:16px; font-weight:900; letter-spacing:3px;")
            h_layout.addWidget(lbl_brand)

        lbl_product = QLabel("SAFX Editor")
        lbl_product.setStyleSheet("color:#89b4fa; font-size:11px; font-weight:600;")
        h_layout.addWidget(lbl_product)

        layout.addWidget(header)

        # Botões: Importar + Configurações
        import_widget = QWidget()
        import_widget.setStyleSheet("background:#181825; padding:8px;")
        import_widget.setFixedHeight(52)
        import_layout = QHBoxLayout(import_widget)
        import_layout.setContentsMargins(8, 4, 8, 4)
        import_layout.setSpacing(6)

        self.btn_import = QPushButton("+ Importar SAFX")
        self.btn_import.setFixedHeight(34)
        self.btn_import.setObjectName("sidebarImportBtn")
        self.btn_import.clicked.connect(self.import_safx)
        import_layout.addWidget(self.btn_import)

        self._btn_settings_sidebar = QPushButton("⚙")
        self._btn_settings_sidebar.setFixedSize(34, 34)
        self._btn_settings_sidebar.setObjectName("sidebarGearBtn")
        self._btn_settings_sidebar.setToolTip("Configurações (Ctrl+,)")
        self._btn_settings_sidebar.clicked.connect(self._open_settings)
        import_layout.addWidget(self._btn_settings_sidebar)

        self._import_widget_ref = import_widget   # ref para refresh_theme

        layout.addWidget(import_widget)

        # Label "TABELAS"
        lbl_section = QLabel("  TABELAS CARREGADAS")
        lbl_section.setProperty("class", "section")
        lbl_section.setStyleSheet(
            "color:#6c7086; font-size:10px; font-weight:700; "
            "padding:8px 12px 4px 12px; letter-spacing:1px;")
        lbl_section.setFixedHeight(28)
        layout.addWidget(lbl_section)

        # Lista de tabelas
        self.table_list = QListWidget()
        self.table_list.setSpacing(2)
        self.table_list.itemClicked.connect(self._on_table_selected)
        self.table_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_list.customContextMenuRequested.connect(self._show_table_context_menu)
        layout.addWidget(self.table_list)

        # Placeholder
        self.lbl_no_tables = QLabel(
            "Nenhuma tabela\nimportada ainda.\n\n"
            "Importe SAFX .txt ou\nplanilha externa (menu).")
        self.lbl_no_tables.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_tables.setStyleSheet("color:#45475a; font-size:12px; padding:20px;")
        layout.addWidget(self.lbl_no_tables)

        return sidebar

    def _create_main_area(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header da tabela ativa ──
        self.table_header = QWidget()
        self.table_header.setObjectName("mainTableHeader")
        self.table_header.setFixedHeight(44)
        self.table_header.setStyleSheet(
            "background:#13131f; border-bottom:2px solid #313244;")
        th_layout = QHBoxLayout(self.table_header)
        th_layout.setContentsMargins(16, 0, 16, 0)
        th_layout.setSpacing(12)

        self.lbl_active_table = QLabel("Nenhuma tabela selecionada")
        self.lbl_active_table.setStyleSheet(
            "color:#89b4fa; font-size:15px; font-weight:700;")
        th_layout.addWidget(self.lbl_active_table)

        self.lbl_active_info = QLabel("")
        self.lbl_active_info.setStyleSheet("color:#6c7086; font-size:12px;")
        th_layout.addWidget(self.lbl_active_info)

        th_layout.addStretch()

        # Botão chaves
        self.btn_config_keys = QPushButton("🔑 Campos Chave")
        self.btn_config_keys.setVisible(False)
        self.btn_config_keys.clicked.connect(self._configure_key_fields)
        th_layout.addWidget(self.btn_config_keys)

        # Botão exportar
        self.btn_export = QPushButton("📤 Exportar")
        self.btn_export.setProperty("class", "primary")
        self.btn_export.setVisible(False)
        self.btn_export.clicked.connect(self._export_data)
        th_layout.addWidget(self.btn_export)

        layout.addWidget(self.table_header)

        # ── Tab widget (Dados | SQL) ──
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        # Tab Dados
        self.data_panel = DataPanel(self.db)
        self.data_panel.dataModified.connect(self._on_data_modified)
        self.data_panel.selectionChanged.connect(self._on_selection_changed)
        self.tab_widget.addTab(self.data_panel, "  📊 Dados  ")

        # Tab SQL
        self.sql_panel = SQLPanel(self.db)
        self.sql_panel.schemaChanged.connect(self._sync_sidebar_sqlite_tables)
        self.tab_widget.addTab(self.sql_panel, "  🔍 Editor SQL  ")

        # Conecta o sinal de commit do painel de dados
        self.data_panel.changeCommitted.connect(self._on_changes_committed)

        # Tab Estrutura
        self.schema_tab = self._create_schema_tab()
        self.tab_widget.addTab(self.schema_tab, "  ℹ️ Estrutura  ")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        return container

    def _create_schema_tab(self) -> QWidget:
        """Aba de estrutura da tabela."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)

        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.schema_table = QTableWidget()
        self.schema_table.setColumnCount(5)
        self.schema_table.setHorizontalHeaderLabels(
            ["Campo", "Tipo", "Tamanho", "Obrigatório", "Descrição"])
        self.schema_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.schema_table.horizontalHeader().setStretchLastSection(True)
        self.schema_table.setEditTriggers(self.schema_table.EditTrigger.NoEditTriggers)
        self.schema_table.setAlternatingRowColors(True)
        self.schema_table.verticalHeader().setDefaultSectionSize(24)

        layout.addWidget(self.schema_table)
        return widget

    def _setup_menus(self):
        menubar = self.menuBar()

        # ── Arquivo ──
        menu_file = menubar.addMenu("Arquivo")

        act_import = QAction("Importar SAFX (TXT)...", self)
        act_import.setShortcut(QKeySequence("Ctrl+O"))
        act_import.triggered.connect(self.import_safx)
        menu_file.addAction(act_import)

        act_import_multi = QAction("Importar Múltiplos SAFX...", self)
        act_import_multi.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_import_multi.triggered.connect(self.import_multiple_safx)
        menu_file.addAction(act_import_multi)

        act_import_ext = QAction("📊  Importar Planilha Externa (Excel/CSV) para JOIN...", self)
        act_import_ext.setShortcut(QKeySequence("Ctrl+Shift+E"))
        act_import_ext.triggered.connect(self._import_external_table)
        menu_file.addAction(act_import_ext)

        act_import_erp = QAction("🔌  Importar via ERP / Banco de Dados...", self)
        act_import_erp.setShortcut(QKeySequence("Ctrl+Shift+D"))
        act_import_erp.triggered.connect(self._import_from_erp)
        menu_file.addAction(act_import_erp)

        menu_file.addSeparator()

        act_export = QAction("Exportar CSV Homologado...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self._export_data)
        menu_file.addAction(act_export)

        menu_file.addSeparator()

        act_layout = QAction("Configurar Diretório de Layouts...", self)
        act_layout.triggered.connect(self._configure_layout_dir)
        menu_file.addAction(act_layout)

        act_settings = QAction("⚙  Configurações...", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self._open_settings)
        menu_file.addAction(act_settings)

        menu_file.addSeparator()

        act_exit = QAction("Sair", self)
        act_exit.setShortcut(QKeySequence("Alt+F4"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # ── Ferramentas ──
        menu_tools = menubar.addMenu("Ferramentas")

        act_report = QAction("📋  Relatório de Alterações...", self)
        act_report.setShortcut(QKeySequence("Ctrl+R"))
        act_report.triggered.connect(self._show_change_report)
        menu_tools.addAction(act_report)

        menu_tools.addSeparator()

        act_api_toggle = QAction("Iniciar/Parar API REST", self)
        act_api_toggle.triggered.connect(self._toggle_api)
        menu_tools.addAction(act_api_toggle)

        act_api_info = QAction("Informações da API...", self)
        act_api_info.triggered.connect(self._show_api_info)
        menu_tools.addAction(act_api_info)

        menu_tools.addSeparator()

        act_sftp_test = QAction("Testar Conexão SFTP...", self)
        act_sftp_test.triggered.connect(self._test_sftp)
        menu_tools.addAction(act_sftp_test)

        # ── Tabela ──
        menu_table = menubar.addMenu("Tabela")

        act_reload = QAction("Recarregar Tabela", self)
        act_reload.setShortcut(QKeySequence("F5"))
        act_reload.triggered.connect(self._reload_current_table)
        menu_table.addAction(act_reload)

        act_close_table = QAction("Fechar Tabela", self)
        act_close_table.triggered.connect(self._close_current_table)
        menu_table.addAction(act_close_table)

        act_close_all = QAction("Fechar Todas as Tabelas", self)
        act_close_all.triggered.connect(self._close_all_tables)
        menu_table.addAction(act_close_all)

        menu_table.addSeparator()

        act_keys = QAction("Configurar Campos Chave...", self)
        act_keys.triggered.connect(self._configure_key_fields)
        menu_table.addAction(act_keys)

        # ── Ver ──
        menu_view = menubar.addMenu("Ver")

        act_dados = QAction("Aba Dados", self)
        act_dados.setShortcut(QKeySequence("Ctrl+1"))
        act_dados.triggered.connect(lambda: self.tab_widget.setCurrentIndex(0))
        menu_view.addAction(act_dados)

        act_sql = QAction("Aba SQL", self)
        act_sql.setShortcut(QKeySequence("Ctrl+2"))
        act_sql.triggered.connect(lambda: self.tab_widget.setCurrentIndex(1))
        menu_view.addAction(act_sql)

        # ── Ajuda ──
        menu_help = menubar.addMenu("Ajuda")
        act_about = QAction("Sobre o SAFX Editor", self)
        act_about.triggered.connect(self._show_about)
        menu_help.addAction(act_about)

    def _setup_toolbar(self):
        toolbar = self.addToolBar("Principal")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))

        act_import = QAction("📂 Importar", self)
        act_import.setToolTip("Importar arquivo SAFX TXT (Ctrl+O)")
        act_import.triggered.connect(self.import_safx)
        toolbar.addAction(act_import)

        toolbar.addSeparator()

        act_export = QAction("📤 Exportar", self)
        act_export.setToolTip("Exportar CSV homologado (Ctrl+E)")
        act_export.triggered.connect(self._export_data)
        toolbar.addAction(act_export)

        toolbar.addSeparator()

        act_sql = QAction("🔍 SQL", self)
        act_sql.setToolTip("Abrir editor SQL (Ctrl+2)")
        act_sql.triggered.connect(lambda: self.tab_widget.setCurrentIndex(1))
        toolbar.addAction(act_sql)

        toolbar.addSeparator()

        act_refresh = QAction("🔄 Atualizar", self)
        act_refresh.setToolTip("Recarregar tabela (F5)")
        act_refresh.triggered.connect(self._reload_current_table)
        toolbar.addAction(act_refresh)

        toolbar.addSeparator()

        act_report = QAction("📋 Relatório", self)
        act_report.setToolTip("Relatório de Alterações (Ctrl+R)")
        act_report.triggered.connect(self._show_change_report)
        toolbar.addAction(act_report)

        toolbar.addSeparator()

        # Toggle Claro/Escuro
        self._act_theme = QAction("☀ Claro", self)
        self._act_theme.setToolTip("Alternar entre tema Claro e Escuro")
        self._act_theme.triggered.connect(self._toggle_theme)
        toolbar.addAction(self._act_theme)
        self._sync_theme_action()

    def _toggle_theme(self):
        current = self.cfg.get_value("ui", "theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        self.cfg.set_value("ui", "theme", new_theme)
        self._apply_style()
        self._sync_theme_action()

    def _sync_theme_action(self):
        theme = self.cfg.get_value("ui", "theme", "dark")
        if theme == 'light':
            self._act_theme.setText("🌙 Escuro")
            self._act_theme.setToolTip("Alternar para tema Escuro")
        else:
            self._act_theme.setText("☀ Claro")
            self._act_theme.setToolTip("Alternar para tema Claro")

    def _apply_style(self):
        from ui.styles import get_style
        theme = self.cfg.get_value("ui", "theme", "dark")
        QApplication.instance().setStyleSheet(get_style(theme))
        # Deixa o stylesheet aplicar antes de repintar painéis (menos “travamento” perceptível)
        QTimer.singleShot(0, lambda t=theme: self._broadcast_theme(t))

    def _broadcast_theme(self, theme: str):
        """Propaga mudança de tema para painéis com estilos próprios."""
        dark = theme != 'light'
        # Sidebar (import button + gear)
        self._apply_sidebar_theme(dark)
        # Painel de dados principal
        if hasattr(self, 'data_panel') and self.data_panel is not None:
            self.data_panel.refresh_theme(theme)
        # Todos os painéis nos tabs
        if hasattr(self, 'tab_widget'):
            for i in range(self.tab_widget.count()):
                w = self.tab_widget.widget(i)
                if hasattr(w, 'refresh_theme'):
                    w.refresh_theme(theme)
        # SQL panel
        if hasattr(self, 'sql_panel') and hasattr(self.sql_panel, 'refresh_theme'):
            self.sql_panel.refresh_theme(theme)
        self._apply_main_header_theme(theme)

    def _apply_main_header_theme(self, theme: str):
        """Cabeçalho da tabela ativa: contraste explícito em claro e escuro."""
        dark = theme != 'light'
        if dark:
            bg = "#16162a"
            bd = "#45475a"
            title = "#b8d8ff"
            subtitle = "#b4bcd8"
            btn_bg = "#2a2a42"
            btn_bd = "#6c7086"
            btn_tx = "#f0f0f8"
            btn_hv = "#3d3d58"
            prim_bg = "#89b4fa"
            prim_tx = "#11111a"
            prim_bd = "#b4d0ff"
            prim_hv = "#b4d0ff"
        else:
            bg = "#d8e2f2"
            bd = "#7a8aa8"
            title = "#0a2a5c"
            subtitle = "#2a3548"
            btn_bg = "#ffffff"
            btn_bd = "#3a5a90"
            btn_tx = "#0a1a30"
            btn_hv = "#c8daf0"
            prim_bg = "#1a5ab4"
            prim_tx = "#ffffff"
            prim_bd = "#0d4070"
            prim_hv = "#2468d8"

        if not hasattr(self, 'table_header'):
            return
        self.table_header.setStyleSheet(
            f"QWidget#mainTableHeader{{background:{bg};border-bottom:2px solid {bd};}}")
        self.lbl_active_table.setStyleSheet(
            f"color:{title};font-size:15px;font-weight:700;background:transparent;")
        self.lbl_active_info.setStyleSheet(
            f"color:{subtitle};font-size:12px;background:transparent;")
        self.btn_config_keys.setStyleSheet(
            f"QPushButton{{background:{btn_bg};color:{btn_tx};"
            f"border:2px solid {btn_bd};border-radius:6px;padding:6px 14px;font-weight:700;}}"
            f"QPushButton:hover{{background:{btn_hv};}}")
        self.btn_export.setStyleSheet(
            f"QPushButton{{background:{prim_bg};color:{prim_tx};"
            f"border:2px solid {prim_bd};border-radius:6px;padding:6px 16px;font-weight:800;}}"
            f"QPushButton:hover{{background:{prim_hv};color:{prim_tx};}}")

    def _apply_sidebar_theme(self, dark: bool):
        """Atualiza estilos do sidebar (botão Importar + engrenagem)."""
        if dark:
            imp_bg  = "#1e4a8a"; imp_tx = "#ffffff"
            imp_hv  = "#2a5fa0"
            gear_bg = "#313244"; gear_tx = "#89b4fa"; gear_hv = "#45475a"
            bar_bg  = "#181825"
        else:
            imp_bg  = "#1a5faa"; imp_tx = "#ffffff"
            imp_hv  = "#2370c0"
            gear_bg = "#dde1ea"; gear_tx = "#1a5faa"; gear_hv = "#c8cfe4"
            bar_bg  = "#dde1ea"

        if hasattr(self, 'btn_import'):
            self.btn_import.setStyleSheet(
                f"QPushButton{{background:{imp_bg};color:{imp_tx};border:none;"
                f"border-radius:6px;font-size:13px;font-weight:700;padding:0 8px;}}"
                f"QPushButton:hover{{background:{imp_hv};}}")
        if hasattr(self, '_btn_settings_sidebar'):
            self._btn_settings_sidebar.setStyleSheet(
                f"QPushButton{{background:{gear_bg};color:{gear_tx};border:none;"
                f"border-radius:6px;font-size:16px;}}"
                f"QPushButton:hover{{background:{gear_hv};}}")
        if hasattr(self, '_import_widget_ref'):
            self._import_widget_ref.setStyleSheet(
                f"background:{bar_bg}; padding:8px;")

    def _update_ui_state(self):
        has_table = self._current_table is not None
        has_safx_layout = (
            has_table and self._current_table in self.db.loaded_tables)
        self.btn_export.setVisible(has_safx_layout)
        self.btn_config_keys.setVisible(has_safx_layout)
        has_tables = bool(self.db.get_loaded_tables()) or bool(
            self.db.list_external_tables())
        self.lbl_no_tables.setVisible(not has_tables)

    def _update_layout_dir_label(self):
        exists = Path(self._layout_dir).exists()
        color = "#a6e3a1" if exists else "#f38ba8"
        self.lbl_layout_dir.setStyleSheet(
            f"color:{color}; font-size:11px; padding:0 8px;")
        self.lbl_layout_dir.setText(
            f"Layout: {Path(self._layout_dir).name}"
            + (" ✓" if exists else " ⚠ não encontrado"))

    # ─── Importação ───────────────────────────────────────────────────────────

    def import_safx(self):
        """Abre diálogo para importar um arquivo SAFX."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Importar SAFX TXT",
            "", "Arquivos TXT (*.txt);;Todos os arquivos (*)")
        if paths:
            for path in paths:
                self._import_file(path)

    def import_multiple_safx(self):
        """Importa múltiplos arquivos de uma pasta."""
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar pasta com arquivos SAFX")
        if not folder:
            return
        import glob
        files = glob.glob(os.path.join(folder, "SAFX*.txt"))
        if not files:
            QMessageBox.information(self, "Nenhum arquivo",
                                    "Nenhum arquivo SAFX*.txt encontrado na pasta.")
            return
        for path in sorted(files):
            self._import_file(path)

    def _import_file(self, filepath: str):
        """Inicia importação de um arquivo."""
        # Detecta nome da tabela
        detected = self.parser.detect_table_name(filepath)

        # Pede confirmação ao usuário
        if detected:
            table_name, ok = QInputDialog.getText(
                self, "Nome da Tabela",
                f"Arquivo: {Path(filepath).name}\n\nNome da tabela SAFX detectado:",
                text=detected)
        else:
            table_name, ok = QInputDialog.getText(
                self, "Nome da Tabela",
                f"Arquivo: {Path(filepath).name}\n\nInforme o nome da tabela (ex: SAFX07):",
                text="SAFX")

        if not ok or not table_name.strip():
            return

        table_name = table_name.strip().upper()

        # Verifica se layout existe
        layout = self.layout_manager.get_layout(table_name)
        if not layout:
            if not Path(self._layout_dir).exists():
                QMessageBox.warning(
                    self, "Layout não encontrado",
                    f"Diretório de layouts não encontrado:\n{self._layout_dir}\n\n"
                    "Configure o diretório correto em Arquivo > Configurar Diretório de Layouts.")
                return
            resp = QMessageBox.question(
                self, "Layout não encontrado",
                f"Layout para '{table_name}' não encontrado em:\n{self._layout_dir}\n\n"
                "Deseja importar mesmo assim? Os campos serão numerados.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if resp != QMessageBox.StandardButton.Yes:
                return

        # Diálogo de progresso moderno
        from ui.import_progress_dialog import ImportProgressDialog
        theme = self.cfg.get_value("ui", "theme", "dark")
        progress = ImportProgressDialog(table_name, parent=self, theme=theme)
        progress.set_file_info(filepath)

        worker = ImportWorker(self.parser, self.db, filepath, table_name)

        def on_progress(pct: int, msg: str):
            progress.update_progress(pct, msg)

        def on_finished(tname: str, count: int):
            progress.mark_done(count, tname)
            # Auto-fecha após 1.5s se tiver muitas linhas (usuário viu o resultado)
            QTimer.singleShot(1500, progress.accept)
            self._on_table_imported(tname, count)

        def on_error(msg: str):
            progress.close()
            QMessageBox.critical(self, "Erro na Importação",
                                 f"Falha ao importar {table_name}:\n\n{msg}")

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        progress.cancelRequested.connect(worker.terminate)

        self._import_workers.append(worker)
        worker.start()
        progress.exec()

    def _sync_sidebar_sqlite_tables(self):
        """
        Sincroniza a lista lateral com tabelas físicas no SQLite (CREATE/DROP
        no Editor SQL). Adiciona entradas em falta e remove tabelas que deixaram
        de existir.
        """
        try:
            physical = self.db.list_sqlite_user_tables()
        except Exception:
            return
        phys_upper = {t.upper() for t in physical}

        for i in range(self.table_list.count() - 1, -1, -1):
            it = self.table_list.item(i)
            if not isinstance(it, TableSidebarItem):
                continue
            if it.table_name.upper() not in phys_upper:
                self.table_list.takeItem(i)

        have = set()
        for i in range(self.table_list.count()):
            it = self.table_list.item(i)
            if isinstance(it, TableSidebarItem):
                have.add(it.table_name.upper())

        for name in sorted(physical, key=lambda x: x.upper()):
            if name.upper() in have:
                continue
            try:
                n = self.db.count_rows(name)
            except Exception:
                n = 0
            self.table_list.addItem(TableSidebarItem(name, n))
            have.add(name.upper())

    def _on_table_imported(self, table_name: str, count: int):
        """Chamado quando importação finaliza."""
        # Atualiza ou adiciona na sidebar
        for i in range(self.table_list.count()):
            item = self.table_list.item(i)
            if isinstance(item, TableSidebarItem) and item.table_name == table_name:
                item.update_count(count)
                self.table_list.setCurrentItem(item)
                self._select_table(table_name)
                return

        item = TableSidebarItem(table_name, count)
        self.table_list.addItem(item)
        self.table_list.setCurrentItem(item)
        self._select_table(table_name)

        self.status_bar.showMessage(
            f"✓ {table_name} importado — {count:,} registros", 5000)
        self._update_ui_state()

    # ─── Seleção de tabela ────────────────────────────────────────────────────

    def _on_table_selected(self, item: QListWidgetItem):
        if isinstance(item, TableSidebarItem):
            self._select_table(item.table_name)

    def _select_table(self, table_name: str):
        self._current_table = table_name
        layout = self.db.loaded_tables.get(table_name)

        # Atualiza header
        self.lbl_active_table.setText(table_name)
        if layout:
            self.lbl_active_info.setText(
                f"Banco: {layout.bank_table}  |  "
                f"{len(layout.fields)} campos")
        elif table_name in self.db.list_external_tables():
            ncols = len(self.db.get_table_columns(table_name))
            self.lbl_active_info.setText(
                f"Planilha externa  |  {ncols} colunas  |  use no JOIN no SQL")

        # Carrega no painel de dados
        key_fields = self._key_fields.get(table_name, [])
        self.data_panel.load_table(table_name, key_fields)

        # Atualiza SQL panel
        self.sql_panel.update_tables(self.db.get_tables_for_sql_panel())

        # Atualiza aba de estrutura
        self._update_schema_tab(table_name)

        self._update_ui_state()
        self.status_bar.showMessage(
            f"Tabela ativa: {table_name}", 3000)

    def _update_schema_tab(self, table_name: str):
        """Atualiza aba de estrutura com campos da tabela."""
        schema_info = self.db.get_schema_info(table_name)
        self.schema_table.setRowCount(len(schema_info))

        for r, info in enumerate(schema_info):
            from PyQt6.QtWidgets import QTableWidgetItem
            cols = ['campo', 'tipo', 'tamanho', 'obrigatorio', 'descricao']
            for c, key in enumerate(cols):
                val = info.get(key, '')
                item_w = QTableWidgetItem(str(val))
                if key == 'obrigatorio' and val == 'SIM':
                    item_w.setForeground(QColor("#a6e3a1"))
                item_w.setFont(QFont("Consolas", 11))
                self.schema_table.setItem(r, c, item_w)

    # ─── Ações de tabela ─────────────────────────────────────────────────────

    def _show_table_context_menu(self, pos):
        item = self.table_list.itemAt(pos)
        if not item:
            return
        if not isinstance(item, TableSidebarItem):
            return

        from PyQt6.QtWidgets import QMenu
        from ui.styles import get_style
        menu = QMenu(self)
        menu.setStyleSheet(get_style(self.cfg.get_value("ui", "theme", "dark")))

        act_select = menu.addAction("Abrir")
        act_select.triggered.connect(lambda: self._select_table(item.table_name))

        menu.addSeparator()

        act_sql = menu.addAction(f"SELECT * FROM {item.table_name}")
        act_sql.triggered.connect(lambda: self._quick_sql_select(item.table_name))

        menu.addSeparator()

        act_export = menu.addAction("Exportar CSV...")
        act_export.triggered.connect(lambda: self._export_table(item.table_name))

        menu.addSeparator()

        act_close = menu.addAction("Remover Tabela")
        act_close.triggered.connect(lambda: self._close_table(item.table_name))

        menu.exec(self.table_list.mapToGlobal(pos))

    def _quick_sql_select(self, table_name: str):
        # Sem LIMIT: ajuste em massa exige ver todas as linhas no resultado
        sql = f'SELECT * FROM "{table_name}"'
        self.sql_panel.set_query(sql)
        self.tab_widget.setCurrentIndex(1)

    def _reload_current_table(self):
        if self._current_table:
            self.data_panel.refresh()

    def _close_current_table(self):
        if self._current_table:
            self._close_table(self._current_table)

    def _close_table(self, table_name: str):
        self.db.drop_table(table_name)
        for i in range(self.table_list.count()):
            item = self.table_list.item(i)
            if isinstance(item, TableSidebarItem) and item.table_name == table_name:
                self.table_list.takeItem(i)
                break
        if self._current_table == table_name:
            self._current_table = None
            self.lbl_active_table.setText("Nenhuma tabela selecionada")
            self.lbl_active_info.setText("")
        self._update_ui_state()
        self.status_bar.showMessage(f"Tabela {table_name} removida", 3000)

    def _close_all_tables(self):
        names = list(self.db.get_loaded_tables())
        for ext in self.db.list_external_tables():
            if ext not in names:
                names.append(ext)
        for name in names:
            self.db.drop_table(name)
        self.table_list.clear()
        self._current_table = None
        self.lbl_active_table.setText("Nenhuma tabela selecionada")
        self.lbl_active_info.setText("")
        self._update_ui_state()

    # ─── Exportação ──────────────────────────────────────────────────────────

    def _export_data(self):
        if not self._current_table:
            QMessageBox.warning(self, "Atenção", "Selecione uma tabela primeiro.")
            return
        self._export_table(self._current_table)

    def _export_table(self, table_name: str):
        if table_name not in self.db.loaded_tables:
            QMessageBox.information(
                self, "Exportar",
                "A exportação no formato homologado SAFX exige o layout da tabela.\n\n"
                "Para dados de planilha externa, use a aba «Editor SQL», "
                "execute um SELECT e copie ou exporte a partir do resultado.")
            return
        selected_ids = self.data_panel.get_selected_row_ids()
        all_ids = self.data_panel.get_all_filtered_row_ids()

        dlg = ExportDialog(
            self.db, self.exporter, self.layout_manager,
            table_name,
            selected_row_ids=selected_ids,
            all_row_ids=all_ids,
            parent=self)
        dlg.exec()

    # ─── Configurações ────────────────────────────────────────────────────────

    def _configure_key_fields(self):
        if not self._current_table:
            return

        layout = self.db.loaded_tables.get(self._current_table)
        if not layout:
            return

        current_keys = self._key_fields.get(self._current_table, [])
        all_fields = layout.get_field_names()

        # Dialog simples de seleção de campos chave
        from PyQt6.QtWidgets import QDialog, QListWidget, QAbstractItemView
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Campos Chave — {self._current_table}")
        dlg.setMinimumSize(400, 500)
        from ui.styles import get_style as _gs
        dlg.setStyleSheet(_gs(self.cfg.get_value("ui", "theme", "dark")))

        from ui.window_utils import enable_dialog_min_max
        enable_dialog_min_max(dlg)

        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setSpacing(8)
        dlg_layout.setContentsMargins(16, 16, 16, 16)

        lbl = QLabel("Selecione os campos que identificam unicamente o registro (campos chave):")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#cdd6f4; font-size:12px;")
        dlg_layout.addWidget(lbl)

        field_list = QListWidget()
        field_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        field_list.setFont(QFont("Consolas", 11))
        for fname in all_fields:
            item = QListWidgetItem(fname)
            field_list.addItem(item)
            if fname in current_keys:
                item.setSelected(True)
                item.setForeground(QColor("#cba6f7"))
        dlg_layout.addWidget(field_list)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("OK")
        btn_ok.setProperty("class", "primary")
        btn_ok.clicked.connect(dlg.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        dlg_layout.addLayout(btn_layout)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = [field_list.item(i).text()
                        for i in range(field_list.count())
                        if field_list.item(i).isSelected()]
            self._key_fields[self._current_table] = selected
            self.data_panel.set_key_fields(selected)
            self.status_bar.showMessage(
                f"Campos chave de {self._current_table} atualizados", 3000)

    def _configure_layout_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar diretório MANUAL LAYOUT",
            self._layout_dir)
        if folder:
            self._layout_dir = folder
            self.layout_manager.layout_dir = Path(folder)
            self.layout_manager.clear_cache()
            self._update_layout_dir_label()
            self.status_bar.showMessage(
                f"Diretório de layouts atualizado: {folder}", 4000)

    # ─── Eventos ──────────────────────────────────────────────────────────────

    def _on_tab_changed(self, index: int):
        if index == 1:  # SQL
            self.sql_panel.update_tables(self.db.get_tables_for_sql_panel())

    def _on_data_modified(self, row_id: int, field: str, old: str, new: str):
        self.status_bar.showMessage(
            f"✎ Campo '{field}' alterado: '{old}' → '{new}'", 4000)

    def _on_changes_committed(self, changes: list):
        """Chamado quando o usuário clica no botão verde de confirmar."""
        count = len(changes)
        self.status_bar.showMessage(
            f"✓ {count} alteração(ões) confirmada(s) e registrada(s) no relatório", 5000)
        if hasattr(self, 'sql_panel') and self.sql_panel is not None:
            self.sql_panel._update_undo_sql_btn()

    def _show_change_report(self):
        """Abre o diálogo de relatório de alterações."""
        dlg = ChangeReportDialog(self.db, parent=self)
        dlg.exec()

    def _import_external_table(self):
        """Abre diálogo para importar planilha externa (Excel/CSV) para JOIN."""
        from ui.external_import_dialog import ExternalImportDialog
        dlg = ExternalImportDialog(self.db, parent=self)
        dlg.tableImported.connect(self._on_external_table_imported)
        dlg.exec()

    def _import_from_erp(self):
        """Abre diálogo de importação via ERP/banco de dados."""
        from ui.erp_connection_dialog import ERPConnectionDialog
        theme = self.cfg.get_value("ui", "theme", "dark")
        dlg = ERPConnectionDialog(
            self.db, self.layout_manager, parent=self, theme=theme)
        dlg.dataReady.connect(self._on_erp_data_ready)
        dlg.exec()

    def _on_erp_data_ready(self, table_name: str, cols: list, rows: list):
        """Chamado quando dados do ERP são carregados."""
        count = len(rows)
        self._on_table_imported(table_name, count)
        self.status_bar.showMessage(
            f"✔  {table_name} importado via ERP — {count:,} registros", 6000)

    def _on_external_table_imported(self, table_name: str, columns: list):
        """Atualiza UI após importar planilha externa (sidebar + dados, como SAFX)."""
        try:
            try:
                count = self.db.count_rows(table_name)
            except Exception:
                count = 0
            self.status_bar.showMessage(
                f"✔  Tabela externa «{table_name}» — {count:,} linhas, "
                f"{len(columns)} colunas — aberta na aba Dados", 8000)

            for i in range(self.table_list.count()):
                item = self.table_list.item(i)
                if isinstance(item, TableSidebarItem) and item.table_name == table_name:
                    item.is_external = True
                    item.update_count(count)
                    self.table_list.setCurrentItem(item)
                    self._select_table(table_name)
                    self._refresh_sql_table_list(table_name, columns, is_external=True)
                    self.tab_widget.setCurrentIndex(0)
                    self._update_ui_state()
                    return

            item = TableSidebarItem(table_name, count, is_external=True)
            self.table_list.addItem(item)
            self.table_list.setCurrentItem(item)
            self._select_table(table_name)
            self._refresh_sql_table_list(table_name, columns, is_external=True)
            self.tab_widget.setCurrentIndex(0)
            self._update_ui_state()
        except Exception as e:
            logger.exception("Falha ao atualizar UI após importação externa")
            QMessageBox.critical(
                self, "Erro na interface",
                f"A tabela pode ter sido criada, mas a lista lateral falhou:\n{e}")

    def _refresh_sql_table_list(self, table_name: str, columns: list,
                                is_external: bool = False):
        """
        Adiciona a tabela externa à sidebar do SQL panel, se ele estiver ativo.
        """
        try:
            sql_panel = self.sql_panel  # atributo definido em _create_main_area
            if sql_panel and hasattr(sql_panel, 'add_external_table'):
                sql_panel.add_external_table(table_name, columns)
        except AttributeError:
            pass

    def _on_selection_changed(self, row_ids: List[int]):
        count = len(row_ids)
        if count > 0:
            self.status_bar.showMessage(f"{count} linha(s) selecionada(s)")

    def _show_about(self):
        from core.about import ABOUT_HTML, ABOUT_HTML_LIGHT, APP_NAME
        theme = self.cfg.get_value("ui", "theme", "dark")
        html = ABOUT_HTML_LIGHT if theme == 'light' else ABOUT_HTML
        QMessageBox.about(self, f"Sobre o {APP_NAME}", html)

    # ─── Configurações / Settings ─────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _on_settings_changed(self):
        """Aplicar mudanças de configuração em tempo real."""
        # Atualiza layout dir se alterado
        cfg_layout = self.cfg.get_value("general", "layout_dir", "")
        if cfg_layout and cfg_layout != self._layout_dir:
            self._layout_dir = cfg_layout
            self.layout_manager.layout_dir = Path(cfg_layout)
            self.layout_manager.clear_cache()
            self._update_layout_dir_label()

        # Reinicia API se necessário
        api_enabled = self.cfg.get_value("api", "enabled", False)
        if api_enabled and (not self._api_server or not self._api_server.running):
            self._start_api_server()
        elif not api_enabled and self._api_server and self._api_server.running:
            self._stop_api_server()

        self.status_bar.showMessage("Configurações salvas", 3000)

    # ─── API REST ────────────────────────────────────────────────────────────

    def _start_api_server(self):
        api_cfg = self.cfg.api
        self._api_server = APIServer.from_config(
            self.db, api_cfg,
            on_update=lambda table: self._on_api_update(table))

        if not self._api_server.available:
            QMessageBox.warning(
                self, "API indisponível",
                "Instale as dependências para usar a API REST:\n\n"
                "pip install flask flask-cors")
            return

        ok, msg = self._api_server.start()
        port = api_cfg.get("port", 8787)
        if ok:
            self.lbl_api_status.setText(f"● API :{port}")
            self.lbl_api_status.setStyleSheet(
                "color:#a6e3a1; font-size:11px; padding:0 8px; font-weight:700;")
            self.status_bar.showMessage(f"API REST iniciada na porta {port}", 4000)
        else:
            self.lbl_api_status.setText("● API ERRO")
            self.lbl_api_status.setStyleSheet(
                "color:#f38ba8; font-size:11px; padding:0 8px; font-weight:700;")
            QMessageBox.warning(self, "Erro ao iniciar API", msg)

    def _stop_api_server(self):
        if self._api_server:
            self._api_server.stop()
        self.lbl_api_status.setText("● API OFF")
        self.lbl_api_status.setStyleSheet(
            "color:#45475a; font-size:11px; padding:0 8px; font-weight:600;")
        self.status_bar.showMessage("API REST parada", 3000)

    def _toggle_api(self):
        if self._api_server and self._api_server.running:
            self._stop_api_server()
            self.cfg.set_value("api", "enabled", False)
        else:
            if not self._api_server:
                api_cfg = self.cfg.api
                self._api_server = APIServer.from_config(self.db, api_cfg)
            self._start_api_server()
            self.cfg.set_value("api", "enabled", True)

    def _show_api_info(self):
        if not self._api_server or not self._api_server.running:
            QMessageBox.information(
                self, "API REST",
                "A API não está rodando.\n\n"
                "Habilite em: Ferramentas > Iniciar/Parar API REST\n"
                "ou configure em: Arquivo > Configurações > API REST")
            return

        port = self.cfg.get_value("api", "port", 8787)
        tables = self.db.get_loaded_tables()
        QMessageBox.information(
            self, "API REST — Rodando",
            f"<b>Servidor API REST ativo</b><br><br>"
            f"URL: <code>http://localhost:{port}/api/</code><br><br>"
            f"<b>Endpoints:</b><br>"
            f"<code>GET  /api/health</code><br>"
            f"<code>GET  /api/tables</code><br>"
            f"<code>GET  /api/tables/{{tabela}}/data</code><br>"
            f"<code>POST /api/tables/{{tabela}}/update</code><br>"
            f"<code>POST /api/sql</code><br><br>"
            f"<b>Tabelas disponíveis:</b> {', '.join(tables) or 'nenhuma'}<br><br>"
            f"Configure em: Arquivo > Configurações > API REST")

    def _on_api_update(self, table_name: str):
        """Chamado quando dados são atualizados via API."""
        if self._current_table == table_name:
            QTimer.singleShot(100, self.data_panel.refresh)
        self.status_bar.showMessage(
            f"[API] Tabela {table_name} atualizada via REST", 4000)

    # ─── SFTP ────────────────────────────────────────────────────────────────

    def _test_sftp(self):
        sftp_cfg = self.cfg.sftp
        if not sftp_cfg.get("host"):
            QMessageBox.information(
                self, "SFTP não configurado",
                "Configure o SFTP em: Arquivo > Configurações > SFTP")
            return

        from core.sftp_manager import SFTPManager
        mgr = SFTPManager.from_config(sftp_cfg)

        self.status_bar.showMessage("Testando conexão SFTP...", 0)
        QApplication.processEvents()

        ok, msg = mgr.test_connection()
        self.status_bar.showMessage(
            ("SFTP: conexão OK" if ok else "SFTP: falha na conexão"), 4000)
        icon = QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning
        mb = QMessageBox(icon, "Teste SFTP", msg, parent=self)
        mb.exec()

    def closeEvent(self, event):
        # Salva tamanho da janela
        self.cfg.set_section("window", {
            "width": self.width(),
            "height": self.height(),
            "maximized": self.isMaximized(),
        })

        # Para API
        if self._api_server and self._api_server.running:
            self._api_server.stop()

        # Para workers ativos
        for w in self._import_workers:
            if w.isRunning():
                w.terminate()
                w.wait(2000)
        event.accept()
