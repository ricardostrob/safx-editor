"""
Painel de dados: grid de visualização/edição + filtros resizáveis.
"""
import logging
from typing import List, Dict, Optional, Set, Tuple

from PyQt6.QtCore import (Qt, QAbstractTableModel, QModelIndex, QThread,
                           pyqtSignal, QTimer, QSortFilterProxyModel)
from PyQt6.QtGui import QColor, QFont, QBrush, QIcon, QKeySequence
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView,
                              QLineEdit, QPushButton, QLabel, QComboBox,
                              QHeaderView, QAbstractItemView, QFrame,
                              QScrollArea, QSizePolicy, QToolButton,
                              QSpacerItem, QMessageBox, QApplication,
                              QSplitter, QMenu)

from core.database import SAFXDatabase, ROW_ID_COL
from core.layout_manager import TableLayout
from ui.styles import CELL_MODIFIED_BG, CELL_MODIFIED_FG, CELL_KEY_BG, CELL_KEY_FG

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000


class SAFXTableModel(QAbstractTableModel):
    """Model para exibição e edição de dados SAFX."""

    cellChanged = pyqtSignal(int, str, str, str)  # row_id, field, old_val, new_val

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns: List[str] = []
        self._rows: List[tuple] = []
        self._row_id_col_idx: int = 0
        self._modified_cells: Dict[Tuple[int, str], str] = {}  # (row_id, col) → new_val
        self._original_cells: Dict[Tuple[int, str], str] = {}  # valores originais para log
        self._key_fields: Set[str] = set()
        self._layout: Optional[TableLayout] = None

    def load_data(self, columns: List[str], rows: List[tuple],
                  layout: Optional[TableLayout] = None,
                  key_fields: List[str] = None):
        self.beginResetModel()
        self._columns = columns
        self._rows = rows
        self._layout = layout
        self._key_fields = set(key_fields or [])
        self._modified_cells.clear()
        self._original_cells.clear()

        try:
            self._row_id_col_idx = columns.index(ROW_ID_COL)
        except ValueError:
            self._row_id_col_idx = -1

        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                if 0 <= section < len(self._columns):
                    col = self._columns[section]
                    if col == ROW_ID_COL:
                        return '#'
                    if col in self._key_fields:
                        return f'🔑 {col}'
                    return col
            else:
                return str(section + 1)

        if role == Qt.ItemDataRole.ForegroundRole:
            if orientation == Qt.Orientation.Horizontal:
                if 0 <= section < len(self._columns):
                    col = self._columns[section]
                    if col in self._key_fields:
                        return QBrush(QColor(CELL_KEY_FG))

        if role == Qt.ItemDataRole.FontRole:
            if orientation == Qt.Orientation.Horizontal:
                font = QFont()
                font.setPointSize(11)
                font.setBold(True)
                return font

        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if row >= len(self._rows) or col >= len(self._columns):
            return None

        col_name = self._columns[col]
        row_id = self._get_row_id(row)
        value = self._rows[row][col]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            modified = self._modified_cells.get((row_id, col_name))
            if modified is not None:
                return modified
            return str(value) if value is not None else ''

        if role == Qt.ItemDataRole.BackgroundRole:
            if (row_id, col_name) in self._modified_cells:
                return QBrush(QColor(CELL_MODIFIED_BG))
            if col_name in self._key_fields:
                return QBrush(QColor("#1a1a2e"))
            if col_name == ROW_ID_COL:
                return QBrush(QColor("#0d0d1a"))
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            if (row_id, col_name) in self._modified_cells:
                return QBrush(QColor(CELL_MODIFIED_FG))
            if col_name in self._key_fields:
                return QBrush(QColor(CELL_KEY_FG))
            if col_name == ROW_ID_COL:
                return QBrush(QColor("#6c7086"))
            return None

        if role == Qt.ItemDataRole.ToolTipRole:
            if self._layout:
                fd = self._layout.get_field(col_name)
                if fd:
                    return f'{fd.name}\nTipo: {fd.field_type.upper()} | Tamanho: {fd.size_str}\n{fd.description[:120]}'
            return None

        if role == Qt.ItemDataRole.FontRole:
            font = QFont("Consolas", 12)
            if col_name == ROW_ID_COL:
                font.setPointSize(10)
            return font

        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        col = index.column()
        col_name = self._columns[col]
        row_id = self._get_row_id(row)

        if col_name == ROW_ID_COL:
            return False

        original_in_db = str(self._rows[row][col]) if self._rows[row][col] is not None else ''
        old_value = self._modified_cells.get((row_id, col_name), original_in_db)
        new_value = str(value)

        if old_value == new_value:
            return False

        # Guarda valor original (antes de qualquer edição) para o log
        if (row_id, col_name) not in self._original_cells:
            self._original_cells[(row_id, col_name)] = original_in_db

        self._modified_cells[(row_id, col_name)] = new_value
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole,
                                              Qt.ItemDataRole.BackgroundRole,
                                              Qt.ItemDataRole.ForegroundRole])
        self.cellChanged.emit(row_id, col_name, old_value, new_value)
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        col_name = self._columns[index.column()]
        if col_name != ROW_ID_COL:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def _get_row_id(self, row: int) -> int:
        if self._row_id_col_idx >= 0 and row < len(self._rows):
            return self._rows[row][self._row_id_col_idx] or row
        return row

    def get_modified_cells(self) -> Dict[Tuple[int, str], str]:
        return dict(self._modified_cells)

    def get_original_cells(self) -> Dict[Tuple[int, str], str]:
        return dict(self._original_cells)

    def clear_modifications(self):
        self._modified_cells.clear()
        self._original_cells.clear()
        self.layoutChanged.emit()

    def get_selected_row_ids(self, rows: List[int]) -> List[int]:
        return [self._get_row_id(r) for r in rows]

    def get_display_columns(self) -> List[str]:
        return [c for c in self._columns if c != ROW_ID_COL]


class FilterRow(QWidget):
    """Uma linha de filtro: [campo ▼] [valor___________] [×]"""

    removeRequested = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, columns: List[str], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        self.combo = QComboBox()
        self.combo.setFixedWidth(190)
        self.combo.setFixedHeight(34)
        self.combo.setStyleSheet(
            "QComboBox { font-size: 12px; padding: 2px 6px; }")
        for col in columns:
            if col != ROW_ID_COL:
                self.combo.addItem(col)
        self.combo.currentTextChanged.connect(self.changed)
        lay.addWidget(self.combo)

        self.value_edit = QLineEdit()
        self.value_edit.setFixedHeight(34)
        self.value_edit.setStyleSheet(
            "QLineEdit { font-size: 13px; padding: 2px 8px; }")
        self.value_edit.setPlaceholderText("valor  (use | para múltiplos, \"exato\" para igualdade)")
        self.value_edit.setMinimumWidth(180)
        self.value_edit.textChanged.connect(self.changed)
        lay.addWidget(self.value_edit, 1)  # stretch = 1 para ocupar espaço disponível

        btn_remove = QToolButton()
        btn_remove.setText("×")
        btn_remove.setFixedSize(28, 28)
        btn_remove.setStyleSheet(
            "QToolButton{border:none;color:#f38ba8;font-size:18px;"
            "background:transparent;border-radius:4px;}"
            "QToolButton:hover{background:#3a1a2e;}")
        btn_remove.clicked.connect(lambda: self.removeRequested.emit(self))
        lay.addWidget(btn_remove)

    def get_field(self) -> str:
        return self.combo.currentText()

    def get_value(self) -> str:
        return self.value_edit.text().strip()

    def set_columns(self, columns: List[str]):
        current = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        for col in columns:
            if col != ROW_ID_COL:
                self.combo.addItem(col)
        idx = self.combo.findText(current)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)


class FilterBar(QWidget):
    """
    Barra de filtros com MÚLTIPLAS linhas simultâneas.
    Todos os filtros são combinados com AND.
    """

    filterChanged = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns: List[str] = []
        self._rows: List[FilterRow] = []
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_filters)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ══════════════════════════════════════════════
        # TOOLBAR: 2 linhas — botões sempre visíveis
        # Linha 1: título + botões de ação
        # Linha 2: resumo dos filtros ativos
        # ══════════════════════════════════════════════
        toolbar = QWidget()
        toolbar.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")
        tb_outer = QVBoxLayout(toolbar)
        tb_outer.setContentsMargins(8, 4, 8, 4)
        tb_outer.setSpacing(3)

        # — Linha 1: título + botões —
        row1 = QWidget()
        row1_lay = QHBoxLayout(row1)
        row1_lay.setContentsMargins(0, 0, 0, 0)
        row1_lay.setSpacing(6)

        lbl = QLabel("🔎  FILTROS")
        lbl.setStyleSheet(
            "color:#89b4fa; font-size:12px; font-weight:800; letter-spacing:1px;")
        row1_lay.addWidget(lbl)

        row1_lay.addStretch()   # empurra botões para a direita, MAS stretch é antes dos btns

        self.btn_add = QPushButton("+ Adicionar Filtro")
        self.btn_add.setFixedHeight(28)
        self.btn_add.setMinimumWidth(130)
        self.btn_add.setStyleSheet(
            "QPushButton{background:#313244;color:#cdd6f4;border:none;"
            "border-radius:5px;font-size:12px;font-weight:600;padding:0 8px;}"
            "QPushButton:hover{background:#45475a;color:white;}")
        self.btn_add.clicked.connect(self.add_filter_row)
        row1_lay.addWidget(self.btn_add)

        btn_apply = QPushButton("▶ Aplicar")
        btn_apply.setFixedHeight(28)
        btn_apply.setMinimumWidth(80)
        btn_apply.setStyleSheet(
            "QPushButton{background:#1e4a8a;color:#89b4fa;border:none;"
            "border-radius:5px;font-size:12px;font-weight:700;padding:0 8px;}"
            "QPushButton:hover{background:#2a5fa0;color:white;}")
        btn_apply.clicked.connect(self._emit_filters)
        row1_lay.addWidget(btn_apply)

        btn_clear = QPushButton("✕ Limpar Tudo")
        btn_clear.setFixedHeight(28)
        btn_clear.setMinimumWidth(100)
        btn_clear.setStyleSheet(
            "QPushButton{background:#2a1a1a;color:#f38ba8;border:1px solid #45475a;"
            "border-radius:5px;font-size:12px;font-weight:600;padding:0 8px;}"
            "QPushButton:hover{background:#3a2020;color:#ff9fb0;}")
        btn_clear.clicked.connect(self.clear_all)
        row1_lay.addWidget(btn_clear)

        tb_outer.addWidget(row1)

        # — Linha 2: resumo dos filtros ativos —
        self.lbl_active = QLabel("Nenhum filtro ativo — clique em '+ Adicionar Filtro' para começar")
        self.lbl_active.setStyleSheet(
            "color:#6c7086; font-size:11px; font-style:italic;")
        self.lbl_active.setWordWrap(False)
        # Trunca com "..." se muito longo
        self.lbl_active.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        tb_outer.addWidget(self.lbl_active)

        outer.addWidget(toolbar)

        # ── Área de linhas de filtro com scroll ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background:#1a1a2e; border:none; }"
            "QScrollBar:vertical { width: 8px; background:#13131f; }"
            "QScrollBar::handle:vertical { background:#45475a; border-radius:4px; }"
        )

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background:#1a1a2e;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(8, 6, 8, 6)
        self._rows_layout.setSpacing(4)
        self._rows_layout.addStretch()

        self._scroll.setWidget(self._rows_container)
        outer.addWidget(self._scroll)

        # Começa com 1 filtro vazio
        self.add_filter_row()

    def add_filter_row(self):
        row = FilterRow(self._columns)
        row.changed.connect(self._on_changed)
        row.removeRequested.connect(self._remove_row)
        insert_idx = self._rows_layout.count() - 1
        self._rows_layout.insertWidget(insert_idx, row)
        self._rows.append(row)
        self._update_label()

    def _remove_row(self, row: 'FilterRow'):
        if len(self._rows) <= 1:
            row.value_edit.clear()
            return
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        self._emit_filters()

    def _on_changed(self):
        self._timer.start(600)

    def set_columns(self, columns: List[str]):
        self._columns = columns
        for row in self._rows:
            row.set_columns(columns)

    def get_active_filters(self) -> Dict[str, str]:
        result = {}
        for row in self._rows:
            field = row.get_field()
            value = row.get_value()
            if field and value:
                if field in result:
                    result[field] = result[field] + '|' + value
                else:
                    result[field] = value
        return result

    def _emit_filters(self):
        filters = self.get_active_filters()
        self._update_label()
        self.filterChanged.emit(filters)

    def _update_label(self):
        active = {f: v for row in self._rows
                  for f, v in [(row.get_field(), row.get_value())]
                  if f and v}
        if active:
            parts = [f"  {f} = {v[:25]!r}" for f, v in list(active.items())[:6]]
            text = f"✔ {len(active)} filtro(s) ativo(s):  " + "   AND   ".join(parts)
            self.lbl_active.setText(text)
            self.lbl_active.setStyleSheet(
                "color:#89b4fa; font-size:11px; font-weight:600; font-style:normal;")
        else:
            self.lbl_active.setText(
                "Nenhum filtro ativo — clique em '+ Adicionar Filtro' para começar")
            self.lbl_active.setStyleSheet(
                "color:#6c7086; font-size:11px; font-style:italic;")

    def clear_all(self):
        while len(self._rows) > 1:
            row = self._rows[-1]
            self._rows.remove(row)
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        if self._rows:
            self._rows[0].value_edit.clear()
        self._update_label()
        self.filterChanged.emit({})


class DataPanel(QWidget):
    """Painel principal de dados: filtros (resizáveis) + grid + paginação."""

    selectionChanged = pyqtSignal(list)
    dataModified = pyqtSignal(int, str, str, str)   # row_id, field, old, new
    changeCommitted = pyqtSignal(list)               # lista de dicts com as mudanças

    def __init__(self, db: SAFXDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self._table_name: Optional[str] = None
        self._layout: Optional[TableLayout] = None
        self._key_fields: List[str] = []
        self._current_page = 0
        self._total_rows = 0
        self._active_filters: Dict[str, str] = {}
        self._pending_changes: List[Dict] = []  # alterações ainda não commitadas no log

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ═══════════════════════════════════════════════════════════════
        # SPLITTER VERTICAL: [filtros] ↕ [info + tabela]
        # O usuário pode arrastar o divisor para ver mais/menos filtros
        # ═══════════════════════════════════════════════════════════════
        self.filter_splitter = QSplitter(Qt.Orientation.Vertical)
        self.filter_splitter.setHandleWidth(10)
        self.filter_splitter.setStyleSheet(
            # Alça do splitter: barra azul larga e visível com grip points
            "QSplitter::handle:vertical {"
            "  background: #26263a;"
            "  border-top: 1px solid #45475a;"
            "  border-bottom: 1px solid #45475a;"
            "  image: url(none);"
            "}"
            "QSplitter::handle:vertical:hover {"
            "  background: #1e3a5a;"
            "  border-top: 1px solid #89b4fa;"
            "  border-bottom: 1px solid #89b4fa;"
            "}"
            "QSplitter::handle:vertical:pressed {"
            "  background: #2a4a6a;"
            "}")

        # ── Painel de Filtros ──
        filter_panel = QWidget()
        filter_panel.setObjectName("filterPanel")
        filter_panel.setStyleSheet("#filterPanel { background:#1a1a2e; }")
        fp_layout = QVBoxLayout(filter_panel)
        fp_layout.setContentsMargins(0, 0, 0, 0)
        fp_layout.setSpacing(0)

        self.filter_bar = FilterBar()
        self.filter_bar.filterChanged.connect(self._on_filter_changed)
        fp_layout.addWidget(self.filter_bar)

        self.filter_splitter.addWidget(filter_panel)

        # ── Painel de Dados (info + tabela) ──
        data_panel = QWidget()
        data_panel.setObjectName("dataPanel")
        dp_layout = QVBoxLayout(data_panel)
        dp_layout.setContentsMargins(0, 0, 0, 0)
        dp_layout.setSpacing(0)

        # ── Info bar com botão Commit grande ──
        info_bar = QWidget()
        info_bar.setFixedHeight(44)
        info_bar.setStyleSheet("background:#1e1e2e; border-bottom:1px solid #26263a;")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(12, 4, 12, 4)
        info_layout.setSpacing(8)

        self.lbl_rows = QLabel("Nenhuma tabela carregada")
        self.lbl_rows.setStyleSheet("color:#6c7086; font-size:12px;")
        info_layout.addWidget(self.lbl_rows)

        info_layout.addStretch()

        self.lbl_modified = QLabel("")
        self.lbl_modified.setStyleSheet("color:#a6e3a1; font-size:12px; font-weight:600;")
        info_layout.addWidget(self.lbl_modified)

        # ── Botão VERDE de Commit / Salvar ──
        self.btn_save_changes = QPushButton("  ▶  Confirmar Alterações")
        self.btn_save_changes.setFixedHeight(34)
        self.btn_save_changes.setMinimumWidth(200)
        self.btn_save_changes.setVisible(False)
        self.btn_save_changes.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "    stop:0 #40c878, stop:1 #2ea85a);"
            "  color: #001a0a;"
            "  border: none;"
            "  border-radius: 6px;"
            "  font-size: 13px;"
            "  font-weight: 800;"
            "  padding: 0 16px;"
            "  letter-spacing: 0.5px;"
            "}"
            "QPushButton:hover {"
            "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "    stop:0 #52e890, stop:1 #3eca6e);"
            "}"
            "QPushButton:pressed { padding-top: 3px; }")
        self.btn_save_changes.setToolTip("Confirmar e registrar todas as alterações editadas (Ctrl+S)")
        self.btn_save_changes.clicked.connect(self._save_all_changes)
        info_layout.addWidget(self.btn_save_changes)

        self.btn_cancel_changes = QPushButton("✕ Cancelar")
        self.btn_cancel_changes.setFixedHeight(34)
        self.btn_cancel_changes.setFixedWidth(90)
        self.btn_cancel_changes.setVisible(False)
        self.btn_cancel_changes.setStyleSheet(
            "QPushButton{background:#3a1a1a;color:#f38ba8;border:1px solid #f38ba8;"
            "border-radius:6px;font-size:12px;font-weight:700;}"
            "QPushButton:hover{background:#5a2020;}")
        self.btn_cancel_changes.clicked.connect(self._cancel_changes)
        info_layout.addWidget(self.btn_cancel_changes)

        dp_layout.addWidget(info_bar)

        # ── Tabela ──
        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_view.setSortingEnabled(False)
        self.table_view.verticalHeader().setDefaultSectionSize(30)  # linhas mais altas
        self.table_view.verticalHeader().setVisible(True)
        self.table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(False)
        self.table_view.setShowGrid(True)
        self.table_view.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.AnyKeyPressed)

        self.model = SAFXTableModel(self)
        self.model.cellChanged.connect(self._on_cell_changed)
        self.table_view.setModel(self.model)
        self.table_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed)

        # Menu de contexto para edição em lote
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_table_context_menu)

        dp_layout.addWidget(self.table_view)

        self.filter_splitter.addWidget(data_panel)

        filter_panel.setMinimumHeight(70)
        data_panel.setMinimumHeight(200)
        self.filter_splitter.setCollapsible(0, False)
        self.filter_splitter.setCollapsible(1, False)

        # Aplica proporção após a janela ter sido exibida (evita layout comprimido)
        # Guardamos referência para usar em showEvent
        self._filter_panel_ref = filter_panel
        self._data_panel_ref = data_panel

        main_layout.addWidget(self.filter_splitter)

        # ── Paginação ──
        pagination = QWidget()
        pagination.setFixedHeight(38)
        pagination.setStyleSheet("background:#181825; border-top:1px solid #313244;")
        pag_layout = QHBoxLayout(pagination)
        pag_layout.setContentsMargins(12, 4, 12, 4)
        pag_layout.setSpacing(8)

        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_prev.setFixedWidth(100)
        self.btn_prev.clicked.connect(self._prev_page)
        pag_layout.addWidget(self.btn_prev)

        self.lbl_page = QLabel("Página 1")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page.setFixedWidth(120)
        self.lbl_page.setStyleSheet("color:#a6adc8; font-size:12px;")
        pag_layout.addWidget(self.lbl_page)

        self.btn_next = QPushButton("Próxima ▶")
        self.btn_next.setFixedWidth(100)
        self.btn_next.clicked.connect(self._next_page)
        pag_layout.addWidget(self.btn_next)

        pag_layout.addStretch()

        lbl_page_size = QLabel("Linhas/pág:")
        lbl_page_size.setStyleSheet("color:#6c7086; font-size:12px;")
        pag_layout.addWidget(lbl_page_size)

        self.combo_page_size = QComboBox()
        self.combo_page_size.addItems(["500", "1000", "2000", "5000"])
        self.combo_page_size.setCurrentText("1000")
        self.combo_page_size.setFixedWidth(80)
        self.combo_page_size.currentTextChanged.connect(self._on_page_size_changed)
        pag_layout.addWidget(self.combo_page_size)

        main_layout.addWidget(pagination)

    # ─── Layout inicial correto após exibição ─────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        # Aplica proporção correta ao ser exibido pela 1ª vez
        QTimer.singleShot(0, self._apply_splitter_sizes)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Mantém a área de filtros em 110px ao redimensionar
        QTimer.singleShot(0, self._apply_splitter_sizes)

    def _apply_splitter_sizes(self):
        total = self.filter_splitter.height()
        if total > 200:
            sizes = self.filter_splitter.sizes()
            # Só ajusta se a área de filtros estiver muito pequena ou
            # ainda com valor padrão 0 (nunca foi exibido corretamente)
            if sizes[0] < 80 or sizes[0] > 300:
                self.filter_splitter.setSizes([110, total - 110])

    # ─── Carregamento ─────────────────────────────────────────────────────────

    def load_table(self, table_name: str, key_fields: List[str] = None):
        self._table_name = table_name
        self._layout = self.db.loaded_tables.get(table_name)
        self._key_fields = key_fields or []
        self._current_page = 0
        self._active_filters = {}
        self._pending_changes.clear()
        self.filter_bar.clear_all()

        if self._layout:
            self.filter_bar.set_columns(self._layout.get_field_names())
        elif table_name:
            cols = self.db.get_table_columns(table_name)
            self.filter_bar.set_columns(cols)

        self._refresh_data()

    def _refresh_data(self):
        if not self._table_name:
            return

        page_size = int(self.combo_page_size.currentText())
        offset = self._current_page * page_size

        columns, rows = self.db.get_table_data(
            self._table_name,
            filters=self._active_filters,
            limit=page_size,
            offset=offset
        )
        self._total_rows = self.db.count_rows(self._table_name, self._active_filters)

        self.model.load_data(columns, rows, self._layout, self._key_fields)

        for i, col in enumerate(columns[:30]):
            if col == ROW_ID_COL:
                self.table_view.setColumnWidth(i, 50)
            else:
                self.table_view.setColumnWidth(i, 120)

        self._update_info()
        self._update_pagination()

    def _update_info(self):
        page_size = int(self.combo_page_size.currentText())
        start = self._current_page * page_size + 1
        end = min(start + page_size - 1, self._total_rows)
        filter_info = f' | {len(self._active_filters)} filtro(s)' if self._active_filters else ''
        self.lbl_rows.setText(
            f'{self._total_rows:,} registro(s){filter_info} — exibindo {start:,}–{end:,}')

    def _update_pagination(self):
        page_size = int(self.combo_page_size.currentText())
        total_pages = max(1, (self._total_rows + page_size - 1) // page_size)
        self.lbl_page.setText(f'Pág. {self._current_page + 1} / {total_pages}')
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < total_pages - 1)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._refresh_data()

    def _next_page(self):
        page_size = int(self.combo_page_size.currentText())
        total_pages = max(1, (self._total_rows + page_size - 1) // page_size)
        if self._current_page < total_pages - 1:
            self._current_page += 1
            self._refresh_data()

    def _on_page_size_changed(self):
        self._current_page = 0
        self._refresh_data()

    def _on_filter_changed(self, filters: Dict[str, str]):
        self._active_filters = filters
        self._current_page = 0
        self._refresh_data()

    def _on_cell_changed(self, row_id: int, field: str, old_val: str, new_val: str):
        # Atualiza banco imediatamente
        self.db.update_cell(self._table_name, row_id, field, new_val)

        # Guarda para o log quando o usuário confirmar
        self._pending_changes.append({
            'table': self._table_name,
            'row_id': row_id,
            'field': field,
            'old_value': old_val,
            'new_value': new_val,
            'source': 'manual',
        })

        modified = self.model.get_modified_cells()
        count = len(modified)
        if count > 0:
            self.lbl_modified.setText(f'✎ {count} célula(s) modificada(s) — não confirmada(s)')
            self.btn_save_changes.setVisible(True)
            self.btn_cancel_changes.setVisible(True)
            # Pulsa o botão verde para chamar atenção
            self.btn_save_changes.setStyleSheet(
                "QPushButton {"
                "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                "    stop:0 #52e890, stop:1 #3eca6e);"
                "  color: #001a0a; border: none; border-radius: 6px;"
                "  font-size: 13px; font-weight: 800; padding: 0 16px;"
                "  border: 2px solid #a6e3a1;"
                "}")
        else:
            self.lbl_modified.setText('')
            self.btn_save_changes.setVisible(False)
            self.btn_cancel_changes.setVisible(False)

        self.dataModified.emit(row_id, field, old_val, new_val)

    def _save_all_changes(self):
        """Confirma alterações e registra no log."""
        # Registra no change log do banco
        original = self.model.get_original_cells()
        modified = self.model.get_modified_cells()

        committed = []
        for (row_id, field), new_val in modified.items():
            old_val = original.get((row_id, field), '')
            self.db.add_to_change_log(
                table=self._table_name,
                row_id=row_id,
                field=field,
                old_value=old_val,
                new_value=new_val,
                source='manual'
            )
            committed.append({
                'table': self._table_name,
                'row_id': row_id,
                'field': field,
                'old_value': old_val,
                'new_value': new_val,
            })

        self.model.clear_modifications()
        self._pending_changes.clear()

        count = len(committed)
        self.lbl_modified.setText(f'✓ {count} alteração(ões) confirmada(s) e registrada(s) no log')
        self.btn_save_changes.setVisible(False)
        self.btn_cancel_changes.setVisible(False)
        QTimer.singleShot(3000, lambda: self.lbl_modified.setText(''))

        if committed:
            self.changeCommitted.emit(committed)

    def _cancel_changes(self):
        reply = QMessageBox.question(
            self, "Cancelar Edições",
            "Deseja cancelar todas as edições não confirmadas?\n\n"
            "Os dados serão recarregados do banco de dados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._pending_changes.clear()
            self._refresh_data()
            self.lbl_modified.setText('')
            self.btn_save_changes.setVisible(False)
            self.btn_cancel_changes.setVisible(False)

    def _on_selection_changed(self):
        selected_rows = list(set(
            idx.row() for idx in self.table_view.selectedIndexes()
        ))
        row_ids = self.model.get_selected_row_ids(selected_rows)
        self.selectionChanged.emit(row_ids)

    # ─── API pública ──────────────────────────────────────────────────────────

    def get_selected_row_ids(self) -> List[int]:
        selected_rows = list(set(
            idx.row() for idx in self.table_view.selectedIndexes()
        ))
        return self.model.get_selected_row_ids(selected_rows)

    def get_all_filtered_row_ids(self) -> List[int]:
        if not self._table_name:
            return []
        where_parts, params = self.db._build_where(self._active_filters)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f'SELECT "{ROW_ID_COL}" FROM "{self._table_name}" {where_sql}'
        with self.db._lock:
            cur = self.db.conn.cursor()
            cur.execute(sql, list(params))
            return [r[0] for r in cur.fetchall()]

    def set_key_fields(self, key_fields: List[str]):
        self._key_fields = key_fields
        if self._table_name:
            self.model._key_fields = set(key_fields)
            self.model.layoutChanged.emit()

    def refresh(self):
        self._refresh_data()

    def copy_selected(self):
        indexes = self.table_view.selectedIndexes()
        if not indexes:
            return
        rows = sorted({i.row() for i in indexes})
        cols = sorted({i.column() for i in indexes})
        lines = []
        for r in rows:
            cells = []
            for c in cols:
                idx = self.model.index(r, c)
                cells.append(str(self.model.data(idx) or ''))
            lines.append('\t'.join(cells))
        QApplication.clipboard().setText('\n'.join(lines))

    # ─── Menu de contexto e Edição em Lote ───────────────────────────────────

    def _show_table_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        idx = self.table_view.indexAt(pos)
        selected_rows = list({i.row() for i in self.table_view.selectedIndexes()})
        n = len(selected_rows)

        menu = QMenu(self.table_view)
        menu.setStyleSheet(
            "QMenu{background:#1e1e2e;border:1px solid #45475a;"
            "border-radius:6px;padding:4px;}"
            "QMenu::item{padding:6px 20px 6px 12px;color:#cdd6f4;"
            "border-radius:4px;font-size:12px;}"
            "QMenu::item:selected{background:#89b4fa;color:#1e1e2e;}"
            "QMenu::separator{height:1px;background:#45475a;margin:4px 8px;}")

        # Edição em lote — só se há seleção e coluna válida
        if n > 0 and idx.isValid():
            col_name = self.model._columns[idx.column()] if idx.column() < len(self.model._columns) else ''
            if col_name and col_name != ROW_ID_COL:
                act_bulk = menu.addAction(f"✎  Editar em lote — {n} linha(s) no campo '{col_name}'")
                act_bulk.triggered.connect(
                    lambda: self._open_bulk_edit(col_name, selected_rows))
                menu.addSeparator()

        # Copiar
        act_copy = menu.addAction("📋  Copiar células selecionadas")
        act_copy.triggered.connect(self.copy_selected)

        # Selecionar tudo
        act_all = menu.addAction("Selecionar tudo (página atual)")
        act_all.triggered.connect(self.table_view.selectAll)

        if n > 0:
            menu.addSeparator()
            act_desel = menu.addAction("Desmarcar seleção")
            act_desel.triggered.connect(self.table_view.clearSelection)

        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def _open_bulk_edit(self, col_name: str, selected_rows: List[int]):
        from ui.bulk_edit_dialog import BulkEditDialog

        # Pega valor de amostra da primeira linha selecionada
        sample = ''
        if selected_rows:
            first_row = min(selected_rows)
            try:
                col_idx = self.model._columns.index(col_name)
                sample = str(self.model._rows[first_row][col_idx] or '')
            except (ValueError, IndexError):
                sample = ''

        dlg = BulkEditDialog(
            field_name=col_name,
            row_count=len(selected_rows),
            current_sample=sample,
            parent=self
        )

        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        mode, _ = dlg.get_result()

        # Aplica a mudança em todas as linhas selecionadas
        changes_applied = 0
        try:
            col_idx = self.model._columns.index(col_name)
        except ValueError:
            return

        for row_idx in selected_rows:
            row_id = self.model._get_row_id(row_idx)
            current_val = str(self.model._rows[row_idx][col_idx] or '')
            new_val = dlg.compute_new_value(current_val)

            if new_val == current_val:
                continue

            # Atualiza no banco e no model
            self.db.update_cell(self._table_name, row_id, col_name, new_val)
            self.db.add_to_change_log(
                table=self._table_name,
                row_id=row_id,
                field=col_name,
                old_value=current_val,
                new_value=new_val,
                source='bulk'
            )
            # Registra no model (para destaque visual)
            orig = self.model._original_cells.get((row_id, col_name), current_val)
            self.model._original_cells.setdefault((row_id, col_name), orig)
            self.model._modified_cells[(row_id, col_name)] = new_val
            changes_applied += 1

        if changes_applied > 0:
            self.model.layoutChanged.emit()
            self._pending_changes.append({
                'table': self._table_name,
                'field': col_name,
                'mode': mode,
                'rows_affected': changes_applied,
            })
            self.lbl_modified.setText(
                f'✎ {changes_applied} linha(s) alteradas em lote no campo "{col_name}"'
                f' — clique em Confirmar')
            self.btn_save_changes.setVisible(True)
            self.btn_cancel_changes.setVisible(True)

            # Auto-commit: salva automaticamente no change log
            self._save_all_changes()

            QMessageBox.information(
                self, "Edição em Lote Concluída",
                f"✓ {changes_applied} de {len(selected_rows)} linha(s) foram atualizadas\n"
                f"Campo: {col_name}\n"
                f"Modo: {mode}\n\n"
                f"As alterações foram registradas no Relatório de Alterações.")
        else:
            QMessageBox.information(
                self, "Sem Alterações",
                "Nenhuma linha foi alterada (os valores já eram iguais ao novo valor).")
