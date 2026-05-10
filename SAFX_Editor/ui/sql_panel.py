"""
Painel de editor SQL completo com toolbar, commit/rollback, resultados e status.
"""
import logging
import time
from typing import List, Tuple, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRegularExpression, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtGui import (QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
                          QKeySequence, QAction, QIcon)
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                              QPlainTextEdit, QPushButton, QLabel,
                              QTableWidget, QTableWidgetItem, QHeaderView,
                              QFrame, QComboBox, QSizePolicy, QToolButton,
                              QToolBar, QStatusBar, QMessageBox, QApplication,
                              QMenu, QCheckBox, QSpinBox, QTextEdit,
                              QAbstractItemView)

from core.database import SAFXDatabase
from ui.styles import (SQL_KEYWORD_COLOR, SQL_STRING_COLOR, SQL_NUMBER_COLOR,
                       SQL_COMMENT_COLOR, SQL_TABLE_COLOR)

logger = logging.getLogger(__name__)

SQL_KEYWORDS = [
    'SELECT', 'FROM', 'WHERE', 'UPDATE', 'SET', 'INSERT', 'INTO',
    'VALUES', 'DELETE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER',
    'ON', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL',
    'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'OFFSET', 'DISTINCT',
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'AS', 'CASE', 'WHEN', 'THEN',
    'ELSE', 'END', 'CREATE', 'DROP', 'TABLE', 'INDEX', 'PRAGMA',
    'WITH', 'UNION', 'ALL', 'EXCEPT', 'INTERSECT', 'EXISTS',
    'COALESCE', 'IFNULL', 'SUBSTR', 'LENGTH', 'TRIM', 'UPPER', 'LOWER',
    'REPLACE', 'CAST', 'TYPEOF', 'BEGIN', 'COMMIT', 'ROLLBACK',
    'TRANSACTION', 'EXPLAIN', 'QUERY', 'PLAN', 'VACUUM', 'ANALYZE',
    'ALTER', 'ADD', 'COLUMN', 'RENAME', 'TO', 'ATTACH', 'DETACH',
]


class SQLHighlighter(QSyntaxHighlighter):
    """Syntax highlighter para SQL."""

    def __init__(self, document):
        super().__init__(document)
        self._rules = []
        self._build_rules()

    def _fmt(self, color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(700)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _build_rules(self):
        keyword_fmt = self._fmt(SQL_KEYWORD_COLOR, bold=True)
        pattern = r'\b(' + '|'.join(SQL_KEYWORDS) + r')\b'
        self._rules.append((QRegularExpression(
            pattern, QRegularExpression.PatternOption.CaseInsensitiveOption),
            keyword_fmt))

        self._rules.append((QRegularExpression(r"'(?:[^'\\]|\\.)*'"),
                             self._fmt(SQL_STRING_COLOR)))
        self._rules.append((QRegularExpression(r'"(?:[^"\\]|\\.)*"'),
                             self._fmt(SQL_TABLE_COLOR)))
        self._rules.append((QRegularExpression(r'\b\d+(\.\d+)?\b'),
                             self._fmt(SQL_NUMBER_COLOR)))
        self._rules.append((QRegularExpression(
            r'\bSAFX\d+\w*\b',
            QRegularExpression.PatternOption.CaseInsensitiveOption),
            self._fmt(SQL_TABLE_COLOR, bold=True)))
        self._rules.append((QRegularExpression(r'--[^\n]*'),
                             self._fmt(SQL_COMMENT_COLOR, italic=True)))

        self._comment_start = QRegularExpression(r'/\*')
        self._comment_end = QRegularExpression(r'\*/')
        self._comment_fmt = self._fmt(SQL_COMMENT_COLOR, italic=True)

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            m = self._comment_start.match(text)
            start = m.capturedStart() if m.hasMatch() else -1
        while start >= 0:
            m_end = self._comment_end.match(text, start)
            if m_end.hasMatch():
                end = m_end.capturedEnd()
                self.setFormat(start, end - start, self._comment_fmt)
                m_next = self._comment_start.match(text, end)
                start = m_next.capturedStart() if m_next.hasMatch() else -1
            else:
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, self._comment_fmt)
                break


class LineNumberArea(QWidget):
    """Área de números de linha para o editor SQL."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(self.editor._line_number_width(), 0)

    def paintEvent(self, event):
        self.editor._paint_line_numbers(event)


class SQLEditor(QPlainTextEdit):
    """Editor SQL com números de linha, syntax highlight e atalhos."""

    executeRequested = pyqtSignal()
    commitRequested = pyqtSignal()
    rollbackRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont("Consolas", 13)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(40)

        self._highlighter = SQLHighlighter(self.document())

        # Área de números de linha
        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_area_width(0)
        self._highlight_current_line()

        self.setPlaceholderText(
            "-- Editor SQL — SAFX Editor\n"
            "-- F5 ou Ctrl+Enter: Executar | F9: Commit | F10: Rollback\n"
            "-- Ctrl+/: Comentar linha | Ctrl+Space: Sugestão de tabela\n"
            "-- Use aspas duplas para nomes de tabelas: \"SAFX07\"\n\n"
            "SELECT * FROM \"SAFX07\" LIMIT 100"
        )

    def _line_number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance('9') * max(digits, 3)

    def _update_line_area_width(self, _):
        self.setViewportMargins(self._line_number_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(),
                                    self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        from PyQt6.QtCore import QRect
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self._line_number_width(), cr.height()))

    def _paint_line_numbers(self, event):
        from PyQt6.QtGui import QPainter, QColor as QC
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QC("#13131f"))

        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(self.blockBoundingGeometry(block)
                  .translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        font = QFont("Consolas", 10)
        painter.setFont(font)
        current_line = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                num = str(block_num + 1)
                if block_num == current_line:
                    painter.setPen(QC("#89b4fa"))
                else:
                    painter.setPen(QC("#45475a"))
                painter.drawText(
                    0, top,
                    self._line_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, num)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_num += 1

    def _highlight_current_line(self):
        selections = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#26263a"))
            sel.format.setProperty(
                QTextCharFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        self.setExtraSelections(selections)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        # F5 ou Ctrl+Enter = Executar
        if key == Qt.Key.Key_F5 or (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and
                mods & Qt.KeyboardModifier.ControlModifier):
            self.executeRequested.emit()
            return

        # F9 = Commit
        if key == Qt.Key.Key_F9:
            self.commitRequested.emit()
            return

        # F10 = Rollback
        if key == Qt.Key.Key_F10:
            self.rollbackRequested.emit()
            return

        # Ctrl+/ = Toggle comentário de linha
        if key == Qt.Key.Key_Slash and mods & Qt.KeyboardModifier.ControlModifier:
            self._toggle_comment()
            return

        # Tab = 4 espaços
        if key == Qt.Key.Key_Tab and not (mods & Qt.KeyboardModifier.ShiftModifier):
            self.insertPlainText('    ')
            self._refresh_column_completer_if_popup_visible()
            return

        # Shift+Tab = remove 4 espaços
        if key == Qt.Key.Key_Backtab:
            self._unindent()
            self._refresh_column_completer_if_popup_visible()
            return

        super().keyPressEvent(event)
        self._refresh_column_completer_if_popup_visible()

    def _toggle_comment(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.setPosition(start)
        cursor.movePosition(cursor.MoveOperation.StartOfLine)

        cursor.setPosition(end, cursor.MoveMode.KeepAnchor)
        cursor.movePosition(cursor.MoveOperation.EndOfLine,
                             cursor.MoveMode.KeepAnchor)

        text = cursor.selectedText()
        lines = text.split('\u2029')  # Qt paragraph separator
        result = []
        for line in lines:
            if line.lstrip().startswith('--'):
                result.append(line.replace('--', '', 1).lstrip(' '))
            else:
                result.append('-- ' + line)
        cursor.insertText('\u2029'.join(result))
        cursor.endEditBlock()

    def _unindent(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(cursor.MoveOperation.StartOfLine)
        cursor.movePosition(cursor.MoveOperation.Right,
                             cursor.MoveMode.KeepAnchor, 4)
        if cursor.selectedText() == '    ':
            cursor.removeSelectedText()
        cursor.endEditBlock()

    def get_selected_or_all(self) -> str:
        cursor = self.textCursor()
        text = cursor.selectedText().strip()
        if text:
            return text.replace('\u2029', '\n')
        return self.toPlainText().strip()

    def get_current_statement(self) -> str:
        """Retorna a instrução SQL atual (delimitada por ;)."""
        full = self.toPlainText()
        cursor = self.textCursor()
        pos = cursor.position()

        # Encontra início e fim da instrução atual
        start = full.rfind(';', 0, pos)
        start = start + 1 if start >= 0 else 0
        end = full.find(';', pos)
        end = end + 1 if end >= 0 else len(full)

        stmt = full[start:end].strip()
        return stmt if stmt else full.strip()

    def insert_snippet(self, text: str):
        cursor = self.textCursor()
        cursor.insertText(text)
        self.setFocus()


class ResultsTable(QTableWidget):
    """Tabela de resultados SQL com edição inline e atualização no banco."""

    cellEditedInDB = pyqtSignal(str, int, str, str, str)  # table, row_id, field, old, new

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db: Optional['SAFXDatabase'] = None
        self._source_table: str = ''
        self._columns: List[str] = []
        self._row_id_col_idx: int = -1
        self._editable: bool = False
        self._loading: bool = False  # bloqueia cellChanged durante load

        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(self.SelectionBehavior.SelectRows)
        self.setSortingEnabled(True)
        self.verticalHeader().setDefaultSectionSize(28)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        # Edição com um único clique em célula já selecionada
        self.setEditTriggers(
            self.EditTrigger.SelectedClicked |
            self.EditTrigger.AnyKeyPressed |
            self.EditTrigger.DoubleClicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemChanged.connect(self._on_item_changed)

    def setup_for_editing(self, db, source_table: str):
        """Configura o table para edição inline vinculada ao banco."""
        self._db = db
        self._source_table = source_table

    def load_results(self, columns: List[str], rows: List[tuple]):
        self._loading = True
        self.setSortingEnabled(False)
        self.clear()
        self._columns = list(columns)
        self.setRowCount(len(rows))
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)

        # Verifica se tem _row_id para permitir edição real
        try:
            self._row_id_col_idx = columns.index('_row_id')
            self._editable = bool(self._source_table)
        except ValueError:
            self._row_id_col_idx = -1
            self._editable = False

        font = QFont("Consolas", 11)
        color_rowid = QColor("#3a3a5a")
        color_editable = QColor("#1a2a1a")

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                txt = str(val) if val is not None else ''
                item = QTableWidgetItem(txt)
                item.setFont(font)
                col_name = columns[c] if c < len(columns) else ''
                if col_name == '_row_id':
                    item.setBackground(color_rowid)
                    item.setForeground(QColor("#6c7086"))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                elif self._editable:
                    item.setBackground(color_editable)
                self.setItem(r, c, item)

        for i in range(min(len(columns), 25)):
            if columns[i] == '_row_id':
                self.setColumnWidth(i, 55)
            else:
                self.setColumnWidth(i, 120)

        self.setSortingEnabled(True)
        self._loading = False

        # Hint visual sobre edição
        if self._editable:
            self.setToolTip(
                f"Tabela: {self._source_table} — clique em uma célula para editar")
        else:
            self.setToolTip("Resultado somente leitura (sem coluna _row_id)")

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._loading or not self._editable or not self._db:
            return
        if not self._source_table:
            return

        row = item.row()
        col = item.column()
        col_name = self._columns[col] if col < len(self._columns) else ''
        if col_name == '_row_id' or not col_name:
            return

        # Pega o _row_id da mesma linha
        if self._row_id_col_idx < 0:
            return
        rid_item = self.item(row, self._row_id_col_idx)
        if not rid_item:
            return
        try:
            row_id = int(rid_item.text())
        except ValueError:
            return

        new_val = item.text()

        # Busca valor antigo direto do banco
        try:
            from core.database import ROW_ID_COL
            with self._db._lock:
                cur = self._db.conn.cursor()
                cur.execute(
                    f'SELECT "{col_name}" FROM "{self._source_table}" '
                    f'WHERE "{ROW_ID_COL}" = ?', [row_id])
                res = cur.fetchone()
                old_val = str(res[0]) if res and res[0] is not None else ''
        except Exception:
            old_val = ''

        if old_val == new_val:
            return

        # Aplica a atualização no banco
        self._db.update_cell(self._source_table, row_id, col_name, new_val)
        self._db.add_to_change_log(
            table=self._source_table,
            row_id=row_id,
            field=col_name,
            old_value=old_val,
            new_value=new_val,
            source='sql-result'
        )

        # Destaca célula editada
        item.setBackground(QColor("#1a2e1a"))
        item.setForeground(QColor("#a6e3a1"))

        self.cellEditedInDB.emit(
            self._source_table, row_id, col_name, old_val, new_val)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        act_copy = menu.addAction("Copiar células selecionadas")
        act_copy.triggered.connect(self._copy_selected)
        act_copy_all = menu.addAction("Copiar tudo (com cabeçalho)")
        act_copy_all.triggered.connect(self._copy_all)
        if self._editable:
            menu.addSeparator()
            lbl = menu.addAction(f"Tabela fonte: {self._source_table}")
            lbl.setEnabled(False)
        menu.exec(self.mapToGlobal(pos))

    def _copy_selected(self):
        indexes = self.selectedIndexes()
        if not indexes:
            return
        rows = sorted({i.row() for i in indexes})
        cols = sorted({i.column() for i in indexes})
        lines = []
        for r in rows:
            cells = []
            for c in cols:
                item = self.item(r, c)
                cells.append(item.text() if item else '')
            lines.append('\t'.join(cells))
        QApplication.clipboard().setText('\n'.join(lines))

    def _copy_all(self):
        cols = [self.horizontalHeaderItem(i).text()
                for i in range(self.columnCount())]
        lines = ['\t'.join(cols)]
        for r in range(self.rowCount()):
            cells = []
            for c in range(self.columnCount()):
                item = self.item(r, c)
                cells.append(item.text() if item else '')
            lines.append('\t'.join(cells))
        QApplication.clipboard().setText('\n'.join(lines))


class TransactionManager:
    """Delega controle de transação para SAFXDatabase."""

    def __init__(self, db: SAFXDatabase):
        self.db = db

    @property
    def in_transaction(self) -> bool:
        return self.db.in_transaction

    def begin(self) -> Tuple[bool, str]:
        return self.db.begin()

    def commit(self) -> Tuple[bool, str]:
        return self.db.commit()

    def rollback(self) -> Tuple[bool, str]:
        return self.db.rollback()


class SQLPanel(QWidget):
    """Painel completo do editor SQL com toolbar profissional."""

    def __init__(self, db: SAFXDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self.tx = TransactionManager(db)
        self._exec_time = 0.0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ══════════════════════════════════════════════════
        # TOOLBAR PRINCIPAL
        # ══════════════════════════════════════════════════
        toolbar = QWidget()
        toolbar.setFixedHeight(46)
        toolbar.setStyleSheet(
            "background:#13131f; border-bottom:2px solid #313244;")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 4, 8, 4)
        tb.setSpacing(4)

        # ── Executar ──
        self.btn_run = self._make_btn(
            "▶  Executar", "#89b4fa", "#1e1e2e",
            "Executar SQL (F5 ou Ctrl+Enter)", width=110)
        self.btn_run.clicked.connect(self._execute)
        tb.addWidget(self.btn_run)

        tb.addWidget(self._sep())

        # ── Transações ──
        self.btn_begin = self._make_btn(
            "⚡ Begin", "#f9e2af", "#1e1e2e",
            "Iniciar transação manual (BEGIN)", width=90)
        self.btn_begin.clicked.connect(self._begin_transaction)
        tb.addWidget(self.btn_begin)

        self.btn_commit = self._make_btn(
            "✔ Commit", "#a6e3a1", "#1e1e2e",
            "Confirmar alterações (F9)", width=90)
        self.btn_commit.clicked.connect(self._commit)
        self.btn_commit.setEnabled(False)
        tb.addWidget(self.btn_commit)

        self.btn_rollback = self._make_btn(
            "✖ Rollback", "#f38ba8", "#1e1e2e",
            "Desfazer alterações (F10)", width=90)
        self.btn_rollback.clicked.connect(self._rollback)
        self.btn_rollback.setEnabled(False)
        tb.addWidget(self.btn_rollback)

        tb.addWidget(self._sep())

        # ── Utilitários ──
        self.btn_explain = self._make_btn(
            "🔍 Explain", "#cba6f7", "#1e1e2e",
            "Mostrar plano de execução (EXPLAIN QUERY PLAN)", width=90)
        self.btn_explain.clicked.connect(self._explain)
        tb.addWidget(self.btn_explain)

        self.btn_format = self._make_btn(
            "⌥ Formatar", "#a6adc8", "#1e1e2e",
            "Formatar SQL (maiúsculas nas palavras-chave)", width=90)
        self.btn_format.clicked.connect(self._format_sql)
        tb.addWidget(self.btn_format)

        self.btn_comment = self._make_btn(
            "// Comentar", "#6c7086", "#cdd6f4",
            "Comentar/descomentar linha selecionada (Ctrl+/)", width=100)
        self.btn_comment.clicked.connect(self._toggle_comment)
        tb.addWidget(self.btn_comment)

        tb.addWidget(self._sep())

        # ── Snippets ──
        self.btn_snippets = self._make_btn(
            "⬦ Snippets", "#a6adc8", "#1e1e2e",
            "Inserir template SQL pronto", width=90)
        self.btn_snippets.clicked.connect(self._show_snippets_menu)
        tb.addWidget(self.btn_snippets)

        tb.addStretch()

        # ── Seletor de tabelas ──
        lbl_t = QLabel("Tabela:")
        lbl_t.setStyleSheet("color:#6c7086; font-size:11px;")
        tb.addWidget(lbl_t)

        self.combo_tables = QComboBox()
        self.combo_tables.setFixedWidth(150)
        self.combo_tables.setFixedHeight(28)
        self.combo_tables.currentTextChanged.connect(self._on_table_selected)
        tb.addWidget(self.combo_tables)

        tb.addWidget(self._sep())

        # ── Limpar ──
        self.btn_clear = self._make_btn(
            "Limpar", "#45475a", "#cdd6f4",
            "Limpar editor e resultados", width=70)
        self.btn_clear.clicked.connect(self._clear)
        tb.addWidget(self.btn_clear)

        layout.addWidget(toolbar)

        # ══════════════════════════════════════════════════
        # STATUS BAR DE TRANSAÇÃO
        # ══════════════════════════════════════════════════
        self.tx_bar = QWidget()
        self.tx_bar.setFixedHeight(24)
        self.tx_bar.setStyleSheet("background:#0d0d1a;")
        tx_layout = QHBoxLayout(self.tx_bar)
        tx_layout.setContentsMargins(12, 0, 12, 0)
        tx_layout.setSpacing(16)

        self.lbl_tx_status = QLabel("● Auto-commit ativo")
        self.lbl_tx_status.setStyleSheet(
            "color:#a6e3a1; font-size:11px; font-weight:600;")
        tx_layout.addWidget(self.lbl_tx_status)

        self.lbl_tx_hint = QLabel(
            "F5=Executar  |  F9=Commit  |  F10=Rollback  |  Ctrl+/=Comentar")
        self.lbl_tx_hint.setStyleSheet("color:#45475a; font-size:11px;")
        tx_layout.addWidget(self.lbl_tx_hint)

        tx_layout.addStretch()

        self.lbl_exec_time = QLabel("")
        self.lbl_exec_time.setStyleSheet("color:#6c7086; font-size:11px;")
        tx_layout.addWidget(self.lbl_exec_time)

        layout.addWidget(self.tx_bar)

        # ══════════════════════════════════════════════════
        # SPLITTER: EDITOR | RESULTADOS
        # ══════════════════════════════════════════════════
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet(
            "QSplitter::handle { background:#313244; }"
            "QSplitter::handle:hover { background:#89b4fa; }")

        # ── Editor ──
        editor_container = QWidget()
        editor_container.setStyleSheet("background:#181825;")
        ed_layout = QVBoxLayout(editor_container)
        ed_layout.setContentsMargins(0, 0, 0, 0)
        ed_layout.setSpacing(0)

        self.editor = SQLEditor()
        self.editor.executeRequested.connect(self._execute)
        self.editor.commitRequested.connect(self._commit)
        self.editor.rollbackRequested.connect(self._rollback)
        self.editor.setStyleSheet(
            "QPlainTextEdit { background:#181825; color:#cdd6f4; "
            "border:none; padding:4px; }")
        ed_layout.addWidget(self.editor)

        splitter.addWidget(editor_container)

        # ── Resultados ──
        results_container = QWidget()
        results_container.setStyleSheet("background:#1e1e2e;")
        res_layout = QVBoxLayout(results_container)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.setSpacing(0)

        # Header dos resultados
        res_header = QWidget()
        res_header.setFixedHeight(28)
        res_header.setStyleSheet(
            "background:#181825; border-top:2px solid #313244; "
            "border-bottom:1px solid #313244;")
        rh = QHBoxLayout(res_header)
        rh.setContentsMargins(12, 0, 12, 0)
        rh.setSpacing(12)

        lbl_res = QLabel("RESULTADOS")
        lbl_res.setStyleSheet(
            "color:#6c7086; font-size:10px; font-weight:700; letter-spacing:1px;")
        rh.addWidget(lbl_res)

        self.lbl_result_info = QLabel("—")
        self.lbl_result_info.setStyleSheet("color:#a6adc8; font-size:11px;")
        rh.addWidget(self.lbl_result_info)

        rh.addStretch()

        # Botão copiar resultados
        btn_copy_res = QPushButton("Copiar")
        btn_copy_res.setFixedHeight(20)
        btn_copy_res.setFixedWidth(60)
        btn_copy_res.setStyleSheet(
            "QPushButton{background:#313244;color:#a6adc8;border:none;"
            "border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#45475a;color:#cdd6f4;}")
        btn_copy_res.clicked.connect(lambda: self.results_table._copy_all())
        rh.addWidget(btn_copy_res)

        res_layout.addWidget(res_header)

        self.results_table = ResultsTable()
        self.results_table.cellEditedInDB.connect(self._on_result_cell_edited)
        res_layout.addWidget(self.results_table)

        # Área de mensagem (erros / sucesso)
        self.msg_area = QLabel()
        self.msg_area.setWordWrap(True)
        self.msg_area.setStyleSheet(
            "background:#0d0d1a; color:#a6e3a1; padding:10px 16px; "
            "font-family:Consolas; font-size:12px; border-top:1px solid #313244;")
        self.msg_area.setVisible(False)
        self.msg_area.setMinimumHeight(36)
        res_layout.addWidget(self.msg_area)

        splitter.addWidget(results_container)
        splitter.setSizes([280, 320])

        layout.addWidget(splitter)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _make_btn(self, text: str, bg: str, fg: str, tooltip: str,
                  width: int = 90) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        btn.setFixedWidth(width)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(
            f"QPushButton{{background:{bg};color:{fg};border:none;"
            f"border-radius:5px;font-size:12px;font-weight:600;padding:0 6px;}}"
            f"QPushButton:hover{{opacity:0.85;filter:brightness(1.15);}}"
            f"QPushButton:pressed{{padding-top:2px;}}"
            f"QPushButton:disabled{{background:#26263a;color:#45475a;}}")
        return btn

    def _sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setFixedHeight(28)
        sep.setStyleSheet("color:#313244;")
        return sep

    # ─── Execução ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_table_from_sql(sql: str) -> str:
        """Tenta extrair o nome da tabela principal de um SELECT/UPDATE."""
        import re
        # FROM "SAFX07" ou FROM safx07
        m = re.search(r'\bFROM\s+"?(\w+)"?', sql, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        # UPDATE "SAFX07"
        m = re.search(r'\bUPDATE\s+"?(\w+)"?', sql, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return ''

    def _execute(self):
        sql = self.editor.get_selected_or_all()
        if not sql:
            self._show_msg("Nenhum SQL para executar.", error=False)
            return

        self.btn_run.setEnabled(False)
        self.btn_run.setText("...")
        self.results_table.clear()
        self.results_table.setRowCount(0)
        self.msg_area.setVisible(False)
        QApplication.processEvents()

        t0 = time.perf_counter()
        try:
            cols, rows, error = self.db.execute_sql(sql)
            elapsed = time.perf_counter() - t0
            self._exec_time = elapsed
            self.lbl_exec_time.setText(f"Tempo: {elapsed:.3f}s")

            is_error = error and error.lower().startswith('erro')

            if error and not cols:
                self._show_msg(error, error=is_error)
                if not is_error:
                    self.lbl_result_info.setText(error)
                    # Loga DMLs (UPDATE/INSERT/DELETE) no change log
                    upper = sql.strip().upper()
                    if any(upper.startswith(k) for k in ('UPDATE', 'INSERT', 'DELETE')):
                        import re
                        m = re.search(r'(\d+) linha', error)
                        affected = int(m.group(1)) if m else 0
                        self.db.add_sql_to_change_log(sql.strip(), affected)
            else:
                # Configura edição inline se for SELECT simples
                source_table = self._extract_table_from_sql(sql)
                self.results_table.setup_for_editing(self.db, source_table)
                self.results_table.load_results(cols, rows)

                editable_hint = (
                    f"  ✏ editável" if (source_table and '_row_id' in cols) else ""
                )
                info = f"{len(rows):,} linha(s) | {len(cols)} coluna(s){editable_hint}"
                self.lbl_result_info.setText(info)
                self.msg_area.setVisible(False)

        except Exception as e:
            elapsed = time.perf_counter() - t0
            self.lbl_exec_time.setText(f"Tempo: {elapsed:.3f}s")
            self._show_msg(f"Erro inesperado: {e}", error=True)

        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("▶  Executar")
            self._update_tx_ui()

    def _explain(self):
        sql = self.editor.get_selected_or_all()
        if not sql:
            return
        upper = sql.strip().upper()
        if not upper.startswith('EXPLAIN'):
            sql = f"EXPLAIN QUERY PLAN {sql}"
        self.editor.setPlainText(sql)
        self._execute()

    # ─── Transações ──────────────────────────────────────────────────────────

    def _begin_transaction(self):
        ok, msg = self.tx.begin()
        self._show_msg(msg, error=not ok)
        self._update_tx_ui()

    def _commit(self):
        ok, msg = self.tx.commit()
        self._show_msg(msg, error=not ok)
        self._update_tx_ui()

    def _rollback(self):
        reply = QMessageBox.question(
            self, "Confirmar Rollback",
            "Deseja desfazer TODAS as alterações da transação atual?\n\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            ok, msg = self.tx.rollback()
            self._show_msg(msg, error=not ok)
            self._update_tx_ui()

    def _update_tx_ui(self):
        in_tx = self.tx.in_transaction
        self.btn_commit.setEnabled(in_tx)
        self.btn_rollback.setEnabled(in_tx)
        self.btn_begin.setEnabled(not in_tx)

        if in_tx:
            self.lbl_tx_status.setText("● Transacao ATIVA — alteracoes pendentes")
            self.lbl_tx_status.setStyleSheet(
                "color:#f9e2af; font-size:11px; font-weight:700;")
            self.tx_bar.setStyleSheet(
                "background:#1a1000; border-bottom:1px solid #f9e2af;")
        else:
            self.lbl_tx_status.setText("● Auto-commit ativo")
            self.lbl_tx_status.setStyleSheet(
                "color:#a6e3a1; font-size:11px; font-weight:600;")
            self.tx_bar.setStyleSheet("background:#0d0d1a;")

    # ─── Formatação e Snippets ────────────────────────────────────────────────

    def _format_sql(self):
        """Coloca palavras-chave SQL em maiúsculas."""
        sql = self.editor.toPlainText()
        if not sql.strip():
            return
        import re
        for kw in sorted(SQL_KEYWORDS, key=len, reverse=True):
            pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
            sql = pattern.sub(kw, sql)
        self.editor.setPlainText(sql)

    def _toggle_comment(self):
        self.editor._toggle_comment()

    def _show_snippets_menu(self):
        """Abre menu de snippets SQL. Usa QCursor.pos() para compatibilidade macOS."""
        try:
            table = self._current_table()
            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu{background:#1e1e2e;border:1px solid #45475a;padding:4px;}"
                "QMenu::item{padding:6px 20px 6px 12px;color:#cdd6f4;}"
                "QMenu::item:selected{background:#89b4fa;color:#1e1e2e;}"
                "QMenu::item:disabled{color:#6c7086;font-weight:bold;}"
                "QMenu::separator{height:1px;background:#45475a;margin:3px 6px;}")

            def sep(title: str):
                menu.addSeparator()
                a = menu.addAction(f"  {title}")
                a.setEnabled(False)

            def add(label: str, sql: str):
                a = menu.addAction(f"    {label}")
                # Default arg captura sql por valor (evita closure bug)
                a.triggered.connect(lambda checked=False, s=sql:
                                    self.editor.insert_snippet(s))

            sep("SELECT")
            add("SELECT * (100 linhas)",
                f'SELECT * FROM "{table}" LIMIT 100')
            add("SELECT com filtro",
                f'SELECT * FROM "{table}"\nWHERE COD_EMPRESA = \'001\'\nLIMIT 100')
            add("COUNT registros",
                f'SELECT COUNT(*) AS total FROM "{table}"')
            add("GROUP BY empresa/estab",
                f'SELECT COD_EMPRESA, COD_ESTAB, COUNT(*) AS qtd\n'
                f'FROM "{table}"\nGROUP BY COD_EMPRESA, COD_ESTAB')

            sep("UPDATE")
            add("UPDATE campo unico",
                f'UPDATE "{table}"\nSET CAMPO = \'NOVO_VALOR\'\n'
                f'WHERE COD_EMPRESA = \'001\'\n  AND NUM_DOCFIS = \'000001\'')
            add("UPDATE multiplos campos",
                f'UPDATE "{table}"\nSET CAMPO1 = \'VALOR1\',\n'
                f'    CAMPO2 = \'VALOR2\'\nWHERE _row_id = 1')
            add("SELECT antes de UPDATE",
                f'SELECT * FROM "{table}"\n'
                f'WHERE COD_EMPRESA = \'001\' LIMIT 10')

            sep("TRANSACAO")
            add("BEGIN + UPDATE + COMMIT",
                f'BEGIN;\nUPDATE "{table}"\nSET CAMPO = \'VALOR\'\n'
                f'WHERE COD_EMPRESA = \'001\';\nCOMMIT;')
            add("ROLLBACK (desfazer)", 'ROLLBACK;')
            add("COMMIT (confirmar)",  'COMMIT;')

            sep("DIAGNOSTICO")
            add("PRAGMA table_info",   f'PRAGMA table_info("{table}")')
            add("EXPLAIN QUERY PLAN",
                f'EXPLAIN QUERY PLAN SELECT * FROM "{table}" LIMIT 1')
            add("Duplicatas por chave",
                f'SELECT COD_EMPRESA, COD_ESTAB, NUM_DOCFIS, COUNT(*) AS qtd\n'
                f'FROM "{table}"\n'
                f'GROUP BY COD_EMPRESA, COD_ESTAB, NUM_DOCFIS\nHAVING COUNT(*) > 1')

            # QCursor.pos() é mais estável que mapToGlobal em macOS/Qt6
            menu.exec(QCursor.pos())

        except Exception as e:
            logger.error("Snippets menu erro: %s", e, exc_info=True)

    def _current_table(self) -> str:
        t = self.combo_tables.currentText()
        return t if t and t != "-- Tabela --" else "SAFX07"

    def _on_table_selected(self, table: str):
        if table and table != "-- Tabela --":
            current = self.editor.toPlainText().strip()
            if not current:
                self.editor.setPlainText(
                    f'SELECT * FROM "{table}" LIMIT 100')

    def _show_msg(self, text: str, error: bool = False):
        color = "#f38ba8" if error else "#a6e3a1"
        self.msg_area.setStyleSheet(
            f"background:#0d0d1a; color:{color}; padding:10px 16px; "
            f"font-family:Consolas; font-size:12px; border-top:1px solid #313244;")
        self.msg_area.setText(text)
        self.msg_area.setVisible(True)

    def _on_result_cell_edited(self, table: str, row_id: int,
                               field: str, old_val: str, new_val: str):
        """Chamado quando o usuário edita uma célula diretamente no resultado SQL."""
        self._show_msg(
            f"✏ [{table}] _row_id={row_id}  {field}: '{old_val}' → '{new_val}'  "
            f"— alteração aplicada e registrada no log",
            error=False)

    def _clear(self):
        self.editor.clear()
        self.results_table.clear()
        self.results_table.setRowCount(0)
        self.lbl_result_info.setText("—")
        self.msg_area.setVisible(False)
        self.lbl_exec_time.setText("")

    def update_tables(self, tables: List[str]):
        """Atualiza combo de tabelas disponíveis."""
        current = self.combo_tables.currentText()
        self.combo_tables.blockSignals(True)
        self.combo_tables.clear()
        self.combo_tables.addItem("-- Tabela --")
        for t in tables:
            self.combo_tables.addItem(t)
        # Restaura seleção anterior
        idx = self.combo_tables.findText(current)
        if idx >= 0:
            self.combo_tables.setCurrentIndex(idx)
        self.combo_tables.blockSignals(False)

    def set_query(self, sql: str):
        self.editor.setPlainText(sql)
        self.editor.setFocus()

    def add_external_table(self, table_name: str, columns: List[str]):
        """
        Adiciona uma tabela externa importada ao combo de tabelas e insere
        um snippet de JOIN de exemplo no editor SQL.
        """
        # Adiciona ao combo se ainda não estiver
        if self.combo_tables.findText(table_name) < 0:
            self.combo_tables.addItem(f"📊 {table_name}")

        # Insere snippet de JOIN no editor
        current_sql = self.editor.toPlainText().strip()
        safx_tables = list(self.db.loaded_tables.keys()) if hasattr(self.db, 'loaded_tables') else []
        safx_ex = safx_tables[0] if safx_tables else 'SAFX_TABELA'
        col1 = columns[0] if columns else 'COL_0'
        join_snippet = (
            f"\n-- Tabela externa '{table_name}' importada  ({len(columns)} colunas)\n"
            f"-- Exemplo de JOIN:\n"
            f"SELECT s.*, e.*\n"
            f"FROM {safx_ex} s\n"
            f"JOIN {table_name} e\n"
            f"  ON s.COD_ESTAB = e.{col1}\n"
            f"LIMIT 100;\n"
        )
        if not current_sql:
            self.editor.setPlainText(join_snippet.strip())
        else:
            self.editor.appendPlainText(join_snippet)
