"""
Estilos modernos para o SAFX Editor.
Suporte a tema Escuro (padrão) e Claro com alto contraste.
"""

MAIN_STYLE = """
/* ───── BASE ───── */
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "SF Pro Display", Arial, sans-serif;
    font-size: 13px;
}

/* ───── JANELA PRINCIPAL ───── */
QMainWindow {
    background-color: #1e1e2e;
}

QMainWindow::separator {
    background: #313244;
    width: 2px;
    height: 2px;
}

/* ───── MENU BAR ───── */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
    padding: 2px 4px;
}

QMenuBar::item {
    padding: 4px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected, QMenuBar::item:pressed {
    background-color: #313244;
}

QMenu {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QMenu::separator {
    height: 1px;
    background: #45475a;
    margin: 4px 8px;
}

/* ───── TOOLBAR ───── */
QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 4px;
    padding: 4px 8px;
}

QToolBar::separator {
    background: #45475a;
    width: 1px;
    margin: 4px 4px;
}

QToolButton {
    background-color: transparent;
    color: #cdd6f4;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}

QToolButton:hover {
    background-color: #313244;
}

QToolButton:pressed {
    background-color: #89b4fa;
    color: #1e1e2e;
}

/* ───── STATUS BAR ───── */
QStatusBar {
    background-color: #181825;
    color: #6c7086;
    border-top: 1px solid #313244;
    padding: 2px 8px;
    font-size: 12px;
}

/* ───── SIDEBAR (lista de tabelas) ───── */
QListWidget {
    background-color: #181825;
    border: none;
    border-radius: 0;
    color: #cdd6f4;
    outline: none;
}

QListWidget::item {
    padding: 8px 12px;
    border-radius: 6px;
    margin: 1px 4px;
}

QListWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}

QListWidget::item:hover:!selected {
    background-color: #26263a;
}

/* ───── TAB WIDGET ───── */
QTabWidget::pane {
    background-color: #1e1e2e;
    border: none;
    border-top: 2px solid #313244;
}

QTabBar {
    background-color: #181825;
}

QTabBar::tab {
    background-color: #181825;
    color: #6c7086;
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
    min-width: 100px;
}

QTabBar::tab:selected {
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
    background-color: #1e1e2e;
}

QTabBar::tab:hover:!selected {
    color: #cdd6f4;
    background-color: #26263a;
}

/* ───── TABLE VIEW ───── */
QTableView {
    background-color: #1e1e2e;
    gridline-color: #313244;
    color: #cdd6f4;
    border: none;
    selection-background-color: #313244;
    selection-color: #cdd6f4;
    alternate-background-color: #252535;
}

QTableView::item {
    padding: 4px 8px;
    border: none;
}

QTableView::item:selected {
    background-color: #45475a;
    color: #cdd6f4;
}

QTableView::item:selected:focus {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QHeaderView {
    background-color: #181825;
}

QHeaderView::section {
    background-color: #181825;
    color: #a6adc8;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #313244;
    border-bottom: 1px solid #313244;
    font-weight: 600;
    font-size: 12px;
}

QHeaderView::section:hover {
    background-color: #26263a;
    color: #cdd6f4;
}

QHeaderView::section:checked {
    color: #89b4fa;
}

/* ───── SCROLL BARS ───── */
QScrollBar:vertical {
    background: #1e1e2e;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #6c7086;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QScrollBar:horizontal {
    background: #1e1e2e;
    height: 10px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 5px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background: #6c7086;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* ───── LINE EDIT / TEXT EDIT ───── */
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 6px 10px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QLineEdit:focus {
    border: 1px solid #89b4fa;
    background-color: #3a3a52;
}

QLineEdit:read-only {
    background-color: #26263a;
    color: #6c7086;
}

QTextEdit, QPlainTextEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    padding: 4px;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #89b4fa;
}

/* ───── BOTÕES ───── */
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #45475a;
    border-color: #6c7086;
}

QPushButton:pressed {
    background-color: #26263a;
}

QPushButton[class="primary"] {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    font-weight: 600;
}

QPushButton[class="primary"]:hover {
    background-color: #b4d0ff;
}

QPushButton[class="primary"]:pressed {
    background-color: #74a8f7;
}

QPushButton[class="success"] {
    background-color: #a6e3a1;
    color: #1e1e2e;
    border: none;
    font-weight: 600;
}

QPushButton[class="success"]:hover {
    background-color: #b9f0b4;
}

QPushButton[class="danger"] {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
    font-weight: 600;
}

QPushButton[class="danger"]:hover {
    background-color: #f5a0b8;
}

QPushButton:disabled {
    background-color: #26263a;
    color: #45475a;
    border-color: #313244;
}

/* ───── COMBO BOX ───── */
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 6px 10px;
    min-width: 120px;
}

QComboBox:hover {
    border-color: #6c7086;
}

QComboBox:focus {
    border-color: #89b4fa;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #6c7086;
    width: 0;
    height: 0;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    outline: none;
}

/* ───── SPIN BOX ───── */
QSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 6px 10px;
}

/* ───── CHECK BOX ───── */
QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 2px solid #45475a;
    background: #313244;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

/* ───── GROUP BOX ───── */
QGroupBox {
    color: #a6adc8;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: -6px;
    padding: 0 6px;
    color: #89b4fa;
    background: #1e1e2e;
}

/* ───── LABEL ───── */
QLabel {
    color: #cdd6f4;
    background: transparent;
}

QLabel[class="title"] {
    font-size: 16px;
    font-weight: 700;
    color: #89b4fa;
}

QLabel[class="subtitle"] {
    font-size: 12px;
    color: #6c7086;
}

QLabel[class="section"] {
    font-size: 11px;
    font-weight: 600;
    color: #a6adc8;
    text-transform: uppercase;
    letter-spacing: 1px;
}

QLabel[class="badge"] {
    background-color: #313244;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    color: #89b4fa;
}

/* ───── SPLITTER ───── */
QSplitter::handle {
    background: #313244;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}

QSplitter::handle:hover {
    background: #89b4fa;
}

/* ───── PROGRESS BAR ───── */
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
    font-size: 11px;
    height: 8px;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}

/* ───── DIALOG ───── */
QDialog {
    background-color: #1e1e2e;
}

/* ───── FRAME ───── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #313244;
}

/* ───── TOOLTIP ───── */
QToolTip {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ───── MESSAGE BOX ───── */
QMessageBox {
    background-color: #1e1e2e;
}

QMessageBox QLabel {
    color: #cdd6f4;
}
"""

# ── Tema Claro ────────────────────────────────────────────────────────────────
LIGHT_STYLE = """
/* ───── BASE ───── */
QWidget {
    background-color: #f0f2f5;
    color: #1a1a2e;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QMainWindow { background-color: #e8eaf0; }
QMainWindow::separator { background: #c8cbd8; width: 2px; height: 2px; }

/* ── MENU ── */
QMenuBar { background: #dde1ea; color: #1a1a2e; border-bottom: 1px solid #b8bcd0; padding: 2px 4px; }
QMenuBar::item { padding: 4px 12px; border-radius: 4px; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: #c8cbdc; }
QMenu { background: #f0f2f5; border: 1px solid #b8bcd0; border-radius: 6px; padding: 4px; }
QMenu::item { padding: 6px 28px 6px 12px; border-radius: 4px; color: #1a1a2e; }
QMenu::item:selected { background: #4a90d9; color: white; }
QMenu::separator { height: 1px; background: #c8cbd8; margin: 4px 8px; }

/* ── TOOLBAR ── */
QToolBar { background: #dde1ea; border-bottom: 1px solid #b8bcd0; spacing: 2px; padding: 2px 8px; }
QToolBar::separator { background: #b8bcd0; width: 1px; margin: 4px 4px; }
QToolButton { color: #1a1a2e; border-radius: 5px; padding: 5px 8px; font-weight: 600; }
QToolButton:hover { background: #c8cbdc; }
QToolButton:checked { background: #4a90d9; color: white; }

/* ── SIDEBAR ── */
QListWidget { background: #e0e4ed; border: none; border-right: 1px solid #b8bcd0; color: #1a1a2e; outline: none; }
QListWidget::item { padding: 8px 12px; border-radius: 5px; margin: 2px 4px; color: #1a1a2e; }
QListWidget::item:selected { background: #4a90d9; color: white; }
QListWidget::item:hover { background: #c8cbdc; }

/* ── TABS ── */
QTabWidget::pane { background: #f0f2f5; border: 1px solid #b8bcd0; border-radius: 0 6px 6px 6px; }
QTabBar::tab { background: #d8dce8; color: #3a3a5e; padding: 8px 20px; border: 1px solid #b8bcd0; border-bottom: none; border-radius: 6px 6px 0 0; margin-right: 2px; font-weight: 600; }
QTabBar::tab:selected { background: #f0f2f5; color: #1a1a2e; border-bottom: 2px solid #4a90d9; }
QTabBar::tab:hover { background: #c8cbdc; }

/* ── TABLE ── */
QTableView, QTableWidget { background: white; color: #1a1a2e; gridline-color: #d0d4e0; border: 1px solid #b8bcd0; border-radius: 4px; selection-background-color: #4a90d9; selection-color: white; }
QHeaderView::section { background: #dde1ea; color: #1a1a2e; font-weight: 700; padding: 6px 8px; border: none; border-right: 1px solid #b8bcd0; border-bottom: 2px solid #4a90d9; }
QTableView::item:hover { background: #e8f0fa; }

/* ── INPUTS ── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: white; color: #1a1a2e;
    border: 1px solid #b8bcd0; border-radius: 5px; padding: 4px 8px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: #4a90d9; }
QComboBox { background: white; color: #1a1a2e; border: 1px solid #b8bcd0; border-radius: 5px; padding: 4px 8px; }
QComboBox:focus { border-color: #4a90d9; }
QComboBox::drop-down { border-left: 1px solid #b8bcd0; }
QComboBox QAbstractItemView { background: white; color: #1a1a2e; selection-background-color: #4a90d9; selection-color: white; }
QSpinBox { background: white; color: #1a1a2e; border: 1px solid #b8bcd0; border-radius: 5px; padding: 4px 8px; }

/* ── BUTTONS ── */
QPushButton { background: #dde1ea; color: #1a1a2e; border: 1px solid #b8bcd0; border-radius: 6px; padding: 5px 14px; font-weight: 600; }
QPushButton:hover { background: #4a90d9; color: white; border-color: #4a90d9; }
QPushButton:pressed { background: #3a7ac9; color: white; }
QPushButton:disabled { background: #e8eaf0; color: #9090a0; border-color: #c8cbd8; }

/* ── SCROLLBARS ── */
QScrollBar:vertical { background: #e8eaf0; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #b8bcd0; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4a90d9; }
QScrollBar:horizontal { background: #e8eaf0; height: 10px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #b8bcd0; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }

/* ── MISC ── */
QProgressBar { background: #d0d4e0; border: none; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #4a90d9; border-radius: 4px; }
QDialog { background: #f0f2f5; }
QGroupBox { color: #1a1a2e; border: 1px solid #b8bcd0; border-radius: 6px; margin-top: 8px; padding: 8px; }
QGroupBox::title { color: #1a1a2e; padding: 0 6px; }
QCheckBox { color: #1a1a2e; }
QRadioButton { color: #1a1a2e; }
QLabel { color: #1a1a2e; }
QStatusBar { background: #dde1ea; color: #1a1a2e; border-top: 1px solid #b8bcd0; }
QToolTip { background: white; color: #1a1a2e; border: 1px solid #b8bcd0; border-radius: 4px; padding: 4px 8px; }
QSplitter::handle { background: #c8cbd8; }
QSplitter::handle:hover { background: #4a90d9; }
"""

# ── Seletor de tema ────────────────────────────────────────────────────────────

def get_style(theme: str = 'dark') -> str:
    """Retorna a folha de estilo para o tema solicitado."""
    return LIGHT_STYLE if theme == 'light' else MAIN_STYLE


def get_cell_colors(theme: str = 'dark') -> dict:
    if theme == 'light':
        return {
            'modified_bg': '#c8f0d8',
            'modified_fg': '#0a6630',
            'key_bg':      '#e8d8f8',
            'key_fg':      '#5a1a8e',
        }
    return {
        'modified_bg': '#1a472a',
        'modified_fg': '#a6e3a1',
        'key_bg':      '#2a1a3e',
        'key_fg':      '#cba6f7',
    }


def get_sql_colors(theme: str = 'dark') -> dict:
    if theme == 'light':
        return {
            'keyword':  '#1a5ab4',
            'string':   '#1a7a3a',
            'number':   '#a04010',
            'comment':  '#707090',
            'table':    '#a06000',
        }
    return {
        'keyword':  '#89b4fa',
        'string':   '#a6e3a1',
        'number':   '#fab387',
        'comment':  '#6c7086',
        'table':    '#f9e2af',
    }


# Cores para destaque de células modificadas (mapeadas por tema via get_cell_colors)
CELL_MODIFIED_BG = "#1a472a"
CELL_MODIFIED_FG = "#a6e3a1"
CELL_KEY_BG = "#2a1a3e"
CELL_KEY_FG = "#cba6f7"

# SQL Syntax highlight colors
SQL_KEYWORD_COLOR = "#89b4fa"
SQL_STRING_COLOR = "#a6e3a1"
SQL_NUMBER_COLOR = "#fab387"
SQL_COMMENT_COLOR = "#6c7086"
SQL_TABLE_COLOR = "#f9e2af"
