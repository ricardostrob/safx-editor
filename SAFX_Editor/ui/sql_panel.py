"""
Painel de editor SQL completo com toolbar, commit/rollback, resultados e status.
"""
import logging
import re
import sqlite3
import time
from typing import Dict, List, Tuple, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRegularExpression, QTimer, QStringListModel
from PyQt6.QtGui import (QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
                          QKeySequence, QAction, QIcon, QTextCursor)
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                              QPlainTextEdit, QPushButton, QLabel,
                              QTableWidget, QTableWidgetItem, QHeaderView,
                              QFrame, QComboBox, QSizePolicy, QToolButton,
                              QToolBar, QStatusBar, QMessageBox, QApplication,
                              QMenu, QCheckBox, QSpinBox, QTextEdit,
                              QAbstractItemView, QDialog, QCompleter)

from core.database import (
    SAFXDatabase, ROW_ID_COL, strip_leading_sql_line_comments, format_sqlite_error,
)

logger = logging.getLogger(__name__)

# Palavras que não são alias após nome de tabela (ex.: FROM SAFX08 WHERE …)
_SQL_TABLE_NEXT_WORDS = frozenset({
    'WHERE', 'GROUP', 'ORDER', 'LIMIT', 'HAVING', 'INNER', 'LEFT', 'RIGHT',
    'FULL', 'CROSS', 'JOIN', 'ON', 'UNION', 'EXCEPT', 'INTERSECT',
    'OFFSET', 'FETCH', 'WINDOW', 'QUALIFY', 'FOR', 'INTO', 'VALUES',
})

_SKIP_EXPLAIN_PREFIXES = (
    'BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE', 'VACUUM', 'ANALYZE',
    'ATTACH', 'DETACH', 'PRAGMA',
)


def _all_known_table_names(db: SAFXDatabase) -> List[str]:
    """Tabelas SAFX carregadas + externas + tabelas físicas no SQLite (ex.: backup por SQL)."""
    names = list(db.loaded_tables.keys())
    for ext in db.list_external_tables():
        if ext not in names:
            names.append(ext)
    if hasattr(db, 'list_sqlite_user_tables'):
        for t in db.list_sqlite_user_tables():
            if t not in names:
                names.append(t)
    return names


def _sql_script_may_change_schema(sql: str) -> bool:
    """True se o script contém CREATE/DROP/ALTER (qualquer instrução)."""
    for chunk in sql.split(';'):
        h = strip_leading_sql_line_comments(chunk.strip()).upper()
        if not h:
            continue
        tok = h.split(None, 1)[0]
        if tok in ('CREATE', 'DROP', 'ALTER'):
            return True
    return False


def _canonical_table_name(raw: str, known: List[str]) -> Optional[str]:
    """Resolve nome citado ou não contra tabelas conhecidas (case-insensitive)."""
    t = raw.strip()
    if t.startswith('"') and t.endswith('"') and len(t) >= 2:
        t = t[1:-1]
    elif t.startswith('`') and t.endswith('`') and len(t) >= 2:
        t = t[1:-1]
    elif t.startswith('[') and t.endswith(']') and len(t) >= 2:
        t = t[1:-1]
    for name in known:
        if name.upper() == t.upper():
            return name
    return None


def parse_sql_table_aliases(
    sql: str,
    known_tables: List[str],
    db: Optional[SAFXDatabase] = None,
) -> Dict[str, str]:
    """
    Extrai alias -> nome físico da tabela (FROM / JOIN … tabela alias).
    alias em minúsculas -> nome canónico como no SQLite.
    Se ``db`` for passado, tenta resolver nomes via SQLite / tabelas externas.
    """
    aliases: Dict[str, str] = {}
    if not sql:
        return aliases
    if not known_tables and db is None:
        return aliases

    pat = re.compile(
        r'\b(?:FROM|(?:INNER|LEFT|RIGHT|FULL|CROSS)\s+JOIN|JOIN)\s+'
        r'(?P<table>\([^)]+\)|"[^"]+"|`[^`]+`|\[[^\]]+\]|\w+)\s+'
        r'(?:AS\s+)?'
        r'(?P<alias>\w+)\b',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pat.finditer(sql):
        tbl_raw = (m.group('table') or '').strip()
        alias = (m.group('alias') or '').strip()
        if not alias or not tbl_raw:
            continue
        if tbl_raw.startswith('('):
            continue
        if alias.upper() in _SQL_TABLE_NEXT_WORDS:
            continue
        canon = _canonical_table_name(tbl_raw, known_tables)
        if not canon and db is not None:
            try:
                canon = db.resolve_sql_table_name(tbl_raw)
            except Exception:
                canon = None
        if canon:
            aliases[alias.lower()] = canon

    return aliases


def _odd_single_quoted(text: str) -> bool:
    """True se cursor está dentro de literal '…' (heurística simples)."""
    n = 0
    i = 0
    while i < len(text):
        if text[i] == "'":
            if i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            n += 1
        i += 1
    return (n % 2) == 1


def validate_sql_syntax(db: SAFXDatabase, sql: str) -> Tuple[bool, str]:
    """
    Valida sintaxe/preparação via SQLite EXPLAIN (sem executar DML).
    """
    parts = [p.strip() for p in sql.split(';') if p.strip()]
    if not parts:
        return True, ''
    for idx, part in enumerate(parts):
        part = strip_leading_sql_line_comments(part)
        if not part:
            continue
        u = part.lstrip().upper()
        skip = False
        for pfx in _SKIP_EXPLAIN_PREFIXES:
            if u.startswith(pfx + ' ') or u == pfx:
                skip = True
                break
        if skip:
            continue
        if u.startswith('EXPLAIN'):
            explain = part
        else:
            explain = f'EXPLAIN {part}'
        try:
            with db._lock:
                cur = db.conn.execute(explain)
                cur.fetchall()
        except sqlite3.Error as e:
            return False, f'Instrução {idx + 1}:\n{format_sqlite_error(e)}'
    return True, ''


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
    """Syntax highlighter para SQL (cores seguem tema claro/escuro)."""

    def __init__(self, document, theme: str = 'dark'):
        super().__init__(document)
        self._theme = theme
        self._rules: List = []
        self._comment_start = QRegularExpression(r'/\*')
        self._comment_end = QRegularExpression(r'\*/')
        self._comment_fmt = QTextCharFormat()
        self._rebuild_rules()

    def set_theme(self, theme: str):
        if theme == self._theme:
            return
        self._theme = theme
        self._rebuild_rules()
        self.rehighlight()

    def _fmt(self, color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(700)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _rebuild_rules(self):
        from ui.styles import get_sql_colors
        c = get_sql_colors(self._theme)
        self._rules = []
        keyword_fmt = self._fmt(c['keyword'], bold=True)
        pattern = r'\b(' + '|'.join(SQL_KEYWORDS) + r')\b'
        self._rules.append((QRegularExpression(
            pattern, QRegularExpression.PatternOption.CaseInsensitiveOption),
            keyword_fmt))

        self._rules.append((QRegularExpression(r"'(?:[^'\\]|\\.)*'"),
                             self._fmt(c['string'])))
        self._rules.append((QRegularExpression(r'"(?:[^"\\]|\\.)*"'),
                             self._fmt(c['table'])))
        self._rules.append((QRegularExpression(r'\b\d+(\.\d+)?\b'),
                             self._fmt(c['number'])))
        self._rules.append((QRegularExpression(
            r'\bSAFX\d+\w*\b',
            QRegularExpression.PatternOption.CaseInsensitiveOption),
            self._fmt(c['table'], bold=True)))
        self._rules.append((QRegularExpression(r'--[^\n]*'),
                             self._fmt(c['comment'], italic=True)))
        self._comment_fmt = self._fmt(c['comment'], italic=True)

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
    validateRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont("Consolas", 13)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(40)

        self._db: Optional[SAFXDatabase] = None
        self._completer_model = QStringListModel(self)
        self._completer = QCompleter(self)
        self._completer.setModel(self._completer_model)
        self._completer.setWidget(self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion)
        self._completer.setWrapAround(False)
        self._completer.activated.connect(self._insert_column_completion)

        from core.config import AppConfig
        _init_theme = AppConfig.get().get_value("ui", "theme", "dark") or "dark"
        self._highlighter = SQLHighlighter(self.document(), _init_theme)
        self._apply_line_theme(_init_theme)

        # Área de números de linha
        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_area_width(0)
        self._highlight_current_line()

        self.setPlaceholderText(
            "-- Editor SQL — SAFX Editor\n"
            "-- F5 / Ctrl+Enter: Executar | F6: Validar sintaxe | F9: Commit | F10: Rollback\n"
            "-- Após alias + . (ex.: a.) sugere colunas das tabelas importadas\n"
            "-- Ctrl+Space: reabrir sugestões de colunas | Ctrl+/: Comentar linha\n\n"
            "SELECT * FROM \"SAFX07\""
        )

    def set_database(self, db: Optional[SAFXDatabase]):
        """Referência ao banco para autocomplete de colunas (JOIN)."""
        self._db = db

    def _insert_column_completion(self, text: str):
        col = str(text)
        c = self.textCursor()
        pos = c.position()
        doc = self.toPlainText()
        dot = doc.rfind('.', 0, pos)
        if dot < 0:
            return
        c.beginEditBlock()
        c.setPosition(dot + 1)
        c.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        c.insertText(col)
        c.endEditBlock()
        self.setTextCursor(c)

    def _alias_column_prefix(self) -> Optional[Tuple[str, str]]:
        """
        Se o cursor está em ``alias.`` ou ``alias.parte``, retorna
        (alias_minúsculo, prefixo_coluna) senão None.
        """
        pos = self.textCursor().position()
        before = self.toPlainText()[:pos]
        if _odd_single_quoted(before):
            return None
        m = re.search(
            r'([A-Za-z_][A-Za-z0-9_]*)\.(\w*)$',
            before,
        )
        if not m:
            return None
        return m.group(1).lower(), m.group(2)

    def _try_show_column_completer(self) -> bool:
        """Abre popup de colunas se alias. mapear para tabela importada."""
        if not self._db:
            return False
        ctx = self._alias_column_prefix()
        if not ctx:
            return False
        alias, partial = ctx
        known = _all_known_table_names(self._db)
        amap = parse_sql_table_aliases(self.toPlainText(), known, self._db)
        table = amap.get(alias)
        if not table:
            return False
        try:
            cols = self._db.get_table_columns(table)
        except Exception:
            cols = []
        if not cols:
            return False
        words = list(cols) + ['*']
        self._completer_model.setStringList(words)
        self._completer.setCompletionPrefix(partial)
        cr = self.cursorRect()
        cr.setWidth(max(260, self.fontMetrics().horizontalAdvance('M') * 28))
        self._completer.complete(cr)
        return True

    def _refresh_column_completer_if_popup_visible(self):
        """Atualiza prefixo e lista ao digitar após ``alias.`` (estilo PL/SQL Developer)."""
        popup = self._completer.popup()
        if popup is None or not popup.isVisible():
            return
        if not self._db:
            popup.hide()
            return
        ctx = self._alias_column_prefix()
        if not ctx:
            popup.hide()
            return
        alias, partial = ctx
        known = _all_known_table_names(self._db)
        amap = parse_sql_table_aliases(self.toPlainText(), known, self._db)
        table = amap.get(alias)
        if not table:
            popup.hide()
            return
        try:
            cols = self._db.get_table_columns(table)
        except Exception:
            cols = []
        if not cols:
            popup.hide()
            return
        words = list(cols) + ['*']
        self._completer_model.setStringList(words)
        self._completer.setCompletionPrefix(partial)
        cr = self.cursorRect()
        cr.setWidth(max(260, self.fontMetrics().horizontalAdvance('M') * 28))
        self._completer.complete(cr)

    def apply_sql_theme(self, theme: str):
        """Sincroniza syntax highlight, números de linha e linha atual ao tema."""
        self._highlighter.set_theme(theme)
        self._apply_line_theme(theme)

    def _apply_line_theme(self, theme: str):
        dark = theme != 'light'
        if dark:
            self._ln_bg = "#13131f"
            self._ln_cur = "#89b4fa"
            self._ln_dim = "#5c5f77"
            self._cur_line_bg = "#26263a"
        else:
            self._ln_bg = "#e2e6ef"
            self._ln_cur = "#003d99"
            self._ln_dim = "#5a6578"
            self._cur_line_bg = "#d4e0f5"
        if hasattr(self, '_line_area'):
            self._line_area.update()
        self._highlight_current_line()

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
        painter.fillRect(event.rect(), QC(self._ln_bg))

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
                    painter.setPen(QC(self._ln_cur))
                else:
                    painter.setPen(QC(self._ln_dim))
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
            sel.format.setBackground(QColor(self._cur_line_bg))
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

        # F6 = Validar sintaxe (EXPLAIN no SQLite)
        if key == Qt.Key.Key_F6:
            self.validateRequested.emit()
            return

        # Ctrl+Space = sugestões de colunas após alias.
        if key == Qt.Key.Key_Space and mods & Qt.KeyboardModifier.ControlModifier:
            if self._try_show_column_completer():
                return

        # '.' após alias: inserir e abrir lista de colunas
        if key == Qt.Key.Key_Period:
            super().keyPressEvent(event)
            self._try_show_column_completer()
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

        # Desligado: com fundo explícito por célula evita texto ilegível (paleta “alternate”).
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(self.SelectionBehavior.SelectItems)
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)
        # Sem ordenação por cabeçalho: o clique seleciona a coluna inteira para edição em massa.
        self.setSortingEnabled(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.verticalHeader().sectionClicked.connect(self._on_row_header_clicked)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().sectionClicked.connect(self._on_column_header_clicked)
        self.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu)
        self.horizontalHeader().setToolTip(
            "Clique esquerdo: seleciona a coluna inteira (edição em massa).\n"
            "Clique direito: ordenar (texto A-Z, numérico, restaurar ordem).")
        # Edição com um único clique em célula já selecionada
        self.setEditTriggers(
            self.EditTrigger.SelectedClicked |
            self.EditTrigger.AnyKeyPressed |
            self.EditTrigger.DoubleClicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemChanged.connect(self._on_item_changed)
        self._dark = True  # alinhado a apply_theme / refresh_theme

    def setup_for_editing(self, db, source_table: str):
        """Configura o table para edição inline vinculada ao banco."""
        self._db = db
        self._source_table = source_table

    def load_results(self, columns: List[str], rows: List[tuple]):
        self._loading = True
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
        row_bg, row_fg = self._row_id_cell_colors()
        edit_bg, _ = self._editable_cell_colors()
        ro_bg, _ = self._readonly_data_cell_colors()

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                txt = str(val) if val is not None else ''
                item = QTableWidgetItem(txt)
                item.setFont(font)
                item.setData(Qt.ItemDataRole.UserRole, r)
                col_name = columns[c] if c < len(columns) else ''
                if col_name == '_row_id':
                    item.setBackground(row_bg)
                    item.setForeground(row_fg)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                elif self._editable and col_name:
                    item.setBackground(edit_bg)
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
                elif col_name:
                    item.setBackground(ro_bg)
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
                self.setItem(r, c, item)

        for i in range(min(len(columns), 25)):
            if columns[i] == '_row_id':
                self.setColumnWidth(i, 55)
            else:
                self.setColumnWidth(i, 120)

        self._loading = False

        # Hint visual sobre edição
        join_hint = ''
        if len(columns) > 80:
            join_hint = (
                "\n\nJOIN (muitas colunas): linhas com o mesmo produto e «NUM_ITEM» "
                "diferentes não são duplicatas — são itens distintos. "
                "SELECT DISTINCT só remove linhas idênticas em todas as colunas."
            )
        if self._editable:
            self.setToolTip(
                f"Tabela: {self._source_table} — clique numa célula para editar."
                f"{join_hint}")
        else:
            self.setToolTip(
                "Resultado só leitura (sem _row_id único para gravar)."
                f"{join_hint}")

    def refresh_from_db(self):
        """Recarrega valores das linhas visíveis a partir do SQLite (após Desfazer)."""
        if not self._db or not self._source_table or self._row_id_col_idx < 0:
            return
        if not self._columns:
            return
        from core.database import ROW_ID_COL
        self._loading = True
        try:
            names = [c for c in self._columns if c]
            if not names:
                return
            cols_sql = ', '.join(f'"{c}"' for c in names)
            row_bg, row_fg = self._row_id_cell_colors()
            edit_bg, edit_fg = self._editable_cell_colors()
            ro_bg, ro_fg = self._readonly_data_cell_colors()
            with self._db._lock:
                cur = self._db.conn.cursor()
                for r in range(self.rowCount()):
                    rid_item = self.item(r, self._row_id_col_idx)
                    if not rid_item:
                        continue
                    try:
                        rid = int(rid_item.text())
                    except ValueError:
                        continue
                    cur.execute(
                        f'SELECT {cols_sql} FROM "{self._source_table}" '
                        f'WHERE "{ROW_ID_COL}" = ?', (rid,))
                    row = cur.fetchone()
                    if not row:
                        continue
                    edited_bg = QColor("#1a2e1a")
                    edited_fg = QColor("#a6e3a1")
                    for c, val in enumerate(row):
                        if c >= len(self._columns):
                            break
                        it = self.item(r, c)
                        if not it:
                            continue
                        col_name = self._columns[c] if c < len(self._columns) else ''
                        txt = str(val) if val is not None else ''
                        it.setText(txt)
                        if col_name == '_row_id':
                            it.setBackground(row_bg)
                            it.setForeground(row_fg)
                        elif self._editable and col_name:
                            it.setBackground(edit_bg)
                            it.setForeground(edit_fg)
                        elif col_name:
                            it.setBackground(ro_bg)
                            it.setForeground(ro_fg)
        finally:
            self._loading = False

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
        self._db.record_undo_batch([{
            'table': self._source_table,
            'row_id': row_id,
            'field': col_name,
            'old_value': old_val,
            'new_value': new_val,
        }])

        # Destaca célula editada
        item.setBackground(QColor("#1a2e1a"))
        item.setForeground(QColor("#a6e3a1"))

        self.cellEditedInDB.emit(
            self._source_table, row_id, col_name, old_val, new_val)

    def _row_id_cell_colors(self):
        if self._dark:
            return QColor("#313244"), QColor("#bac2de")
        return QColor("#e2e6ee"), QColor("#4a5568")

    def _editable_cell_colors(self):
        if self._dark:
            return QColor("#2d3142"), QColor("#e8ecf4")
        return QColor("#eef2f8"), QColor("#0a1220")

    def _readonly_data_cell_colors(self):
        """Células só leitura — fundo alinhado à grade + texto sempre legível."""
        if self._dark:
            return QColor("#1e1e2e"), QColor("#dce0ea")
        return QColor("#ffffff"), QColor("#0d1520")

    def _reapply_result_cell_colors(self):
        """Após mudar o tema, atualiza cores explícitas nas células já carregadas."""
        if self.rowCount() == 0 or not self._columns:
            return
        edited_bg = QColor("#1a2e1a")
        edited_fg = QColor("#a6e3a1")
        row_bg, row_fg = self._row_id_cell_colors()
        edit_bg, _ = self._editable_cell_colors()
        ro_bg, _ = self._readonly_data_cell_colors()
        for r in range(self.rowCount()):
            for c in range(self.columnCount()):
                item = self.item(r, c)
                if not item:
                    continue
                col_name = self._columns[c] if c < len(self._columns) else ''
                if col_name == '_row_id':
                    item.setBackground(row_bg)
                    item.setForeground(row_fg)
                elif self._editable and col_name:
                    cur_bg = item.background().color()
                    cur_fg = item.foreground().color()
                    if cur_bg == edited_bg and cur_fg == edited_fg:
                        continue
                    item.setBackground(edit_bg)
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
                elif col_name:
                    cur_bg = item.background().color()
                    cur_fg = item.foreground().color()
                    if cur_bg == edited_bg and cur_fg == edited_fg:
                        continue
                    item.setBackground(ro_bg)
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)

    def _on_column_header_clicked(self, logical_index: int):
        if logical_index < 0 or logical_index >= len(self._columns):
            return
        if self._columns[logical_index] == '_row_id':
            return
        self.clearSelection()
        self.selectColumn(logical_index)

    def _on_row_header_clicked(self, logical_index: int):
        self.clearSelection()
        self.selectRow(logical_index)

    def _on_header_context_menu(self, pos):
        """Ordenação da grade de resultados (texto / numérica / ordem original)."""
        header = self.horizontalHeader()
        col = header.logicalIndexAt(pos.x())
        if col < 0 or col >= len(self._columns):
            return
        col_name = self._columns[col]
        menu = QMenu(self)
        t = col_name.replace('&', '&&')
        act_az = menu.addAction(f"Ordenar «{t}» — texto A → Z")
        act_za = menu.addAction(f"Ordenar «{t}» — texto Z → A")
        menu.addSeparator()
        act_na = menu.addAction(f"Ordenar «{t}» — número 0 → 9…")
        act_nd = menu.addAction(f"Ordenar «{t}» — número 9… → 0")
        menu.addSeparator()
        act_rst = menu.addAction("Restaurar ordem carregada (original)")
        chosen = menu.exec(header.mapToGlobal(pos))
        if chosen == act_az:
            self._sort_rows_by_column(col, 'text_asc')
        elif chosen == act_za:
            self._sort_rows_by_column(col, 'text_desc')
        elif chosen == act_na:
            self._sort_rows_by_column(col, 'num_asc')
        elif chosen == act_nd:
            self._sort_rows_by_column(col, 'num_desc')
        elif chosen == act_rst:
            self._restore_original_row_order()

    @staticmethod
    def _sort_primary_key(text: str, mode: str) -> tuple:
        """Chave de ordenação; valores não numéricos em modo número vão ao fim."""
        t = (text or '').strip()
        if mode in ('text_asc', 'text_desc'):
            return (0, t.lower())
        if mode in ('num_asc', 'num_desc'):
            t2 = t.replace(',', '.').replace(' ', '')
            try:
                if t2 == '':
                    return (0, 0.0)
                return (0, float(t2))
            except ValueError:
                return (1, t.lower())
        return (2, t.lower())

    def _sort_rows_by_column(self, col: int, mode: str):
        n, m = self.rowCount(), self.columnCount()
        if n == 0 or col < 0 or col >= m:
            return
        self._loading = True
        try:
            rows_items = []
            for r in range(n):
                rows_items.append([self.takeItem(r, c) for c in range(m)])
            reverse = mode in ('text_desc', 'num_desc')

            def sort_key(i: int) -> tuple:
                row = rows_items[i]
                it = row[col] if col < len(row) else None
                txt = it.text() if it else ''
                pk = self._sort_primary_key(txt, mode)
                orig_it = row[0] if row else None
                orig = 0
                if orig_it is not None:
                    v = orig_it.data(Qt.ItemDataRole.UserRole)
                    try:
                        orig = int(v) if v is not None else i
                    except (TypeError, ValueError):
                        orig = i
                return (*pk, orig)

            order = sorted(range(n), key=sort_key, reverse=reverse)
            for new_r, old_i in enumerate(order):
                for c, it in enumerate(rows_items[old_i]):
                    self.setItem(new_r, c, it)
        finally:
            self._loading = False

    def _restore_original_row_order(self):
        n, m = self.rowCount(), self.columnCount()
        if n == 0:
            return
        self._loading = True
        try:
            rows_items = []
            for r in range(n):
                rows_items.append([self.takeItem(r, c) for c in range(m)])

            def orig_index(i: int) -> int:
                it0 = rows_items[i][0] if rows_items[i] else None
                if not it0:
                    return i
                v = it0.data(Qt.ItemDataRole.UserRole)
                try:
                    return int(v) if v is not None else i
                except (TypeError, ValueError):
                    return i

            order = sorted(range(n), key=orig_index)
            for new_r, old_i in enumerate(order):
                for c, it in enumerate(rows_items[old_i]):
                    self.setItem(new_r, c, it)
        finally:
            self._loading = False

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
            idxs = self.selectedIndexes()
            cols = {i.column() for i in idxs}
            if idxs and len(cols) == 1:
                c0 = list(cols)[0]
                if c0 < len(self._columns) and self._columns[c0] != '_row_id':
                    act_bulk = menu.addAction(
                        "✎  Editar valor em massa (coluna selecionada)…")
                    act_bulk.triggered.connect(self._bulk_edit_selected_column)
        menu.exec(self.mapToGlobal(pos))

    def _bulk_edit_selected_column(self):
        if not self._editable or not self._db or self._row_id_col_idx < 0:
            return
        idxs = self.selectedIndexes()
        if not idxs:
            return
        cols = {i.column() for i in idxs}
        if len(cols) != 1:
            QMessageBox.information(
                self, "Edição em massa",
                "Selecione uma única coluna (por exemplo, clique no cabeçalho da coluna).")
            return
        col = list(cols)[0]
        col_name = self._columns[col]
        if col_name == '_row_id':
            return
        rows = sorted({i.row() for i in idxs})
        from ui.bulk_edit_dialog import BulkEditDialog

        sample = ''
        if rows:
            it0 = self.item(rows[0], col)
            sample = it0.text() if it0 else ''

        dlg = BulkEditDialog(
            field_name=col_name,
            row_count=len(rows),
            current_sample=sample,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._loading = True
        try:
            for row in rows:
                rid_item = self.item(row, self._row_id_col_idx)
                if not rid_item:
                    continue
                try:
                    row_id = int(rid_item.text())
                except ValueError:
                    continue
                cur_item = self.item(row, col)
                if not cur_item:
                    continue
                current_val = cur_item.text()
                new_val = dlg.compute_new_value(current_val)
                if new_val == current_val:
                    continue
                with self._db._lock:
                    cur = self._db.conn.cursor()
                    cur.execute(
                        f'SELECT "{col_name}" FROM "{self._source_table}" '
                        f'WHERE "{ROW_ID_COL}" = ?', [row_id])
                    res = cur.fetchone()
                    old_val = str(res[0]) if res and res[0] is not None else ''
                if old_val == new_val:
                    continue
                self._db.update_cell(self._source_table, row_id, col_name, new_val)
                self._db.add_to_change_log(
                    table=self._source_table,
                    row_id=row_id,
                    field=col_name,
                    old_value=old_val,
                    new_value=new_val,
                    source='sql-bulk',
                )
                cur_item.setText(new_val)
                cur_item.setBackground(QColor("#1a2e1a"))
                cur_item.setForeground(QColor("#a6e3a1"))
        finally:
            self._loading = False

        QMessageBox.information(
            self, "Edição em massa",
            f"Valores atualizados na coluna «{col_name}» para {len(rows)} linha(s) selecionada(s).")

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

    def apply_theme(self, dark: bool):
        """Grade de resultados legível em tema claro e escuro."""
        self._dark = dark
        if dark:
            self.setStyleSheet(
                "QTableWidget{background:#1e1e2e;color:#dce0ea;gridline-color:#313244;"
                "border:none;selection-background-color:#1e3a5a;selection-color:#ffffff;}"
                "QTableWidget::item{color:#dce0ea;}"
                "QTableWidget::item:hover{background:#26263a;color:#dce0ea;}"
                "QTableWidget::item:selected,QTableWidget::item:selected:hover,"
                "QTableWidget::item:selected:focus{background-color:#1e3a5a;color:#ffffff;}"
                "QHeaderView::section{background:#26263a;color:#89b4fa;padding:5px;"
                "border:none;border-right:1px solid #313244;font-weight:700;}")
        else:
            self.setStyleSheet(
                "QTableWidget{background:#ffffff;color:#0d1520;gridline-color:#c0c8d8;"
                "border:none;selection-background-color:#1d4ed8;selection-color:#ffffff;}"
                "QTableWidget::item{color:#0d1520;}"
                "QTableWidget::item:hover{background:#e8f0fa;color:#0a1520;}"
                "QTableWidget::item:selected,QTableWidget::item:selected:hover,"
                "QTableWidget::item:selected:focus{background-color:#1d4ed8;color:#ffffff;}"
                "QHeaderView::section{background:#dde4f0;color:#002060;padding:5px;"
                "border:none;border-right:1px solid #b8c0d0;font-weight:700;}")
        self._reapply_result_cell_colors()


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

    schemaChanged = pyqtSignal()

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
        self._toolbar_sql = toolbar
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

        self.btn_validate = self._make_btn(
            "✓ Validar", "#94e2d5", "#1e1e2e",
            "Validar sintaxe SQL com SQLite (F6) — sem executar", width=90)
        self.btn_validate.clicked.connect(self._validate_sql)
        tb.addWidget(self.btn_validate)

        self.btn_undo_sql = self._make_btn(
            "↩ Desfazer", "#a6adc8", "#1e1e2e",
            "Desfaz o último lote (última edição na grade de resultados ou "
            "último confirmar na aba Dados)", width=100)
        self.btn_undo_sql.clicked.connect(self._undo_last_batch)
        tb.addWidget(self.btn_undo_sql)

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
        self._lbl_sql_table = lbl_t
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
            "F5=Executar  |  F6=Validar  |  F9=Commit  |  F10=Rollback  |  Ctrl+/=Comentar")
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
        self._sql_splitter = splitter                  # ref para refresh_theme
        splitter.setHandleWidth(5)
        splitter.setStyleSheet(
            "QSplitter::handle { background:#313244; }"
            "QSplitter::handle:hover { background:#89b4fa; }")

        # ── Editor ──
        editor_container = QWidget()
        self._editor_container = editor_container      # ref para refresh_theme
        editor_container.setStyleSheet("background:#181825;")
        ed_layout = QVBoxLayout(editor_container)
        ed_layout.setContentsMargins(0, 0, 0, 0)
        ed_layout.setSpacing(0)

        self.editor = SQLEditor()
        self.editor.set_database(self.db)
        self.editor.executeRequested.connect(self._execute)
        self.editor.commitRequested.connect(self._commit)
        self.editor.rollbackRequested.connect(self._rollback)
        self.editor.validateRequested.connect(self._validate_sql)
        self.editor.setStyleSheet(
            "QPlainTextEdit { background:#181825; color:#cdd6f4; "
            "border:none; padding:4px; }")
        ed_layout.addWidget(self.editor)

        splitter.addWidget(editor_container)

        # ── Resultados ──
        results_container = QWidget()
        self._results_container = results_container    # ref para refresh_theme
        results_container.setStyleSheet("background:#1e1e2e;")
        res_layout = QVBoxLayout(results_container)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.setSpacing(0)

        # Header dos resultados
        res_header = QWidget()
        self._res_header_sql = res_header
        res_header.setFixedHeight(28)
        res_header.setStyleSheet(
            "background:#181825; border-top:2px solid #313244; "
            "border-bottom:1px solid #313244;")
        rh = QHBoxLayout(res_header)
        rh.setContentsMargins(12, 0, 12, 0)
        rh.setSpacing(12)

        lbl_res = QLabel("RESULTADOS")
        self._lbl_results_header = lbl_res
        lbl_res.setStyleSheet(
            "color:#6c7086; font-size:10px; font-weight:700; letter-spacing:1px;")
        rh.addWidget(lbl_res)

        self.lbl_result_info = QLabel("—")
        self.lbl_result_info.setStyleSheet("color:#a6adc8; font-size:11px;")
        rh.addWidget(self.lbl_result_info)

        rh.addStretch()

        # Botão copiar resultados
        btn_copy_res = QPushButton("Copiar")
        self._btn_copy_res_sql = btn_copy_res
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

        from core.config import AppConfig
        self.refresh_theme(
            AppConfig.get().get_value("ui", "theme", "dark") or "dark")

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

    def refresh_theme(self, theme: str):
        """Atualiza todo o painel SQL (editor, resultados, barras) ao tema claro/escuro."""
        self._theme = theme
        dark = theme != 'light'
        self.editor.apply_sql_theme(theme)
        self.results_table.apply_theme(dark)

        if dark:
            ed_bg = "#181825"
            res_bg = "#1e1e2e"
            spl_h = "#313244"
            spl_hv = "#89b4fa"
            editor_style = (
                "QPlainTextEdit { background:#181825; color:#cdd6f4; "
                "border:none; padding:4px; }")
            tb_bg = "#13131f"
            tb_bd = "#313244"
            rh_bg = "#181825"
            rh_top = "#45475a"
            rh_bot = "#313244"
            lbl_hdr = "#a6adc8"
            lbl_info = "#cdd6f4"
            btn_cp_bg = "#313244"
            btn_cp_tx = "#e8e8f0"
            btn_cp_hv = "#45475a"
            msg_bg = "#0d0d1a"
            msg_tx = "#a6e3a1"
            msg_top = "#313244"
            lbl_tbl = "#a6adc8"
            exec_c = "#6c7086"
            hint_c = "#6a7088"
        else:
            ed_bg = "#f4f6fa"
            res_bg = "#ffffff"
            spl_h = "#b0b8c8"
            spl_hv = "#2468c8"
            editor_style = (
                "QPlainTextEdit { background:#f4f6fa; color:#0d1520; "
                "border:none; padding:4px; }")
            tb_bg = "#dde4f0"
            tb_bd = "#6a7a90"
            rh_bg = "#e8edf5"
            rh_top = "#7a8aa0"
            rh_bot = "#b8c4d4"
            lbl_hdr = "#1a3050"
            lbl_info = "#0d1a30"
            btn_cp_bg = "#ffffff"
            btn_cp_tx = "#0a2040"
            btn_cp_hv = "#4a90d9"
            msg_bg = "#eef2f8"
            msg_tx = "#0a3a18"
            msg_top = "#a8b8c8"
            lbl_tbl = "#2a3548"
            exec_c = "#3a4558"
            hint_c = "#4a5568"

        if hasattr(self, '_editor_container'):
            self._editor_container.setStyleSheet(f"background:{ed_bg};")
        if hasattr(self, '_results_container'):
            self._results_container.setStyleSheet(f"background:{res_bg};")
        if hasattr(self, '_sql_splitter'):
            self._sql_splitter.setStyleSheet(
                f"QSplitter::handle {{ background:{spl_h}; }}"
                f"QSplitter::handle:hover {{ background:{spl_hv}; }}")
        if hasattr(self, 'editor'):
            self.editor.setStyleSheet(editor_style)

        if hasattr(self, '_toolbar_sql'):
            self._toolbar_sql.setStyleSheet(
                f"background:{tb_bg}; border-bottom:2px solid {tb_bd};")
        if hasattr(self, '_lbl_sql_table'):
            self._lbl_sql_table.setStyleSheet(
                f"color:{lbl_tbl}; font-size:11px; font-weight:600;")
        if hasattr(self, '_res_header_sql'):
            self._res_header_sql.setStyleSheet(
                f"background:{rh_bg}; border-top:2px solid {rh_top}; "
                f"border-bottom:1px solid {rh_bot};")
        if hasattr(self, '_lbl_results_header'):
            self._lbl_results_header.setStyleSheet(
                f"color:{lbl_hdr}; font-size:10px; font-weight:800; "
                "letter-spacing:1px;")
        if hasattr(self, 'lbl_result_info'):
            self.lbl_result_info.setStyleSheet(
                f"color:{lbl_info}; font-size:11px; font-weight:600;")
        if hasattr(self, '_btn_copy_res_sql'):
            self._btn_copy_res_sql.setStyleSheet(
                f"QPushButton{{background:{btn_cp_bg};color:{btn_cp_tx};"
                f"border:1px solid {rh_bot};border-radius:4px;font-size:11px;font-weight:600;}}"
                f"QPushButton:hover{{background:{btn_cp_hv};color:#ffffff;}}")
        if hasattr(self, 'msg_area'):
            self.msg_area.setStyleSheet(
                f"background:{msg_bg}; color:{msg_tx}; padding:10px 16px; "
                f"font-family:Consolas; font-size:12px; border-top:1px solid {msg_top};")
        if hasattr(self, 'lbl_exec_time'):
            self.lbl_exec_time.setStyleSheet(
                f"color:{exec_c}; font-size:11px; font-weight:600;")
        if hasattr(self, 'lbl_tx_hint'):
            self.lbl_tx_hint.setStyleSheet(
                f"color:{hint_c}; font-size:11px; font-weight:600;")

        self._update_tx_ui()

    def _validate_sql(self):
        """Valida sintaxe com EXPLAIN (não executa UPDATE/INSERT/DELETE)."""
        sql = self.editor.get_selected_or_all().strip()
        if not sql:
            sql = self.editor.get_current_statement().strip()
        if not sql:
            self._show_msg("Nada para validar.", error=False)
            return
        ok, err = validate_sql_syntax(self.db, sql)
        if ok:
            self._show_msg(
                "✓ Sintaxe OK — o SQLite preparou a instrução (EXPLAIN) sem erro.",
                error=False)
        else:
            self._show_msg(err, error=True)

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

            err_lo = (error or '').lower()
            is_error = bool(error) and (
                '[erro de execução sql' in err_lo
                or err_lo.startswith('erro sql'))

            if error and not cols:
                self._show_msg(error, error=is_error)
                if not is_error:
                    self.lbl_result_info.setText(error)
                    # Loga DMLs (UPDATE/INSERT/DELETE) no change log
                    sql_for_kind = strip_leading_sql_line_comments(sql.strip())
                    upper = sql_for_kind.upper()
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

            if not is_error and _sql_script_may_change_schema(sql):
                self.update_tables(self.db.get_tables_for_sql_panel())
                self.schemaChanged.emit()

        except Exception as e:
            elapsed = time.perf_counter() - t0
            self.lbl_exec_time.setText(f"Tempo: {elapsed:.3f}s")
            self._show_msg(f"Erro inesperado: {e}", error=True)

        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("▶  Executar")
            self._update_tx_ui()
            self._update_undo_sql_btn()

    def _update_undo_sql_btn(self):
        if hasattr(self, 'btn_undo_sql') and self.db is not None:
            self.btn_undo_sql.setEnabled(self.db.can_undo())

    def _undo_last_batch(self):
        """Desfaz o último lote no SQLite (Dados ou grade de resultados)."""
        if not self.db or not self.db.can_undo():
            self._show_msg(
                "Nada para desfazer. Cada confirmação na aba Dados ou cada edição "
                "na grade de resultados gera um lote desfazível.",
                error=False)
            return
        reply = QMessageBox.question(
            self, "Desfazer último lote",
            "Restaurar no SQLite os valores anteriores ao último lote?\n\n"
            "Inclui o último «Confirmar Alterações» na aba Dados ou a última "
            "edição na grade de resultados desta aba.\n"
            "A grade atual é recarregada a partir do banco.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        ok, msg = self.db.undo_last_batch()
        self.results_table.refresh_from_db()
        self._update_undo_sql_btn()
        self._show_msg(msg, error=not ok)

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

        dark = getattr(self, '_theme', 'dark') != 'light'

        if in_tx:
            self.lbl_tx_status.setText("● Transacao ATIVA — alteracoes pendentes")
            self.lbl_tx_status.setStyleSheet(
                "color:#f9e2af; font-size:11px; font-weight:700;")
            self.tx_bar.setStyleSheet(
                "background:#1a1000; border-bottom:1px solid #f9e2af;")
        else:
            self.lbl_tx_status.setText("● Auto-commit ativo")
            if dark:
                self.lbl_tx_status.setStyleSheet(
                    "color:#a6e3a1; font-size:11px; font-weight:600;")
                self.tx_bar.setStyleSheet(
                    "background:#0d0d1a; border-bottom:1px solid #313244;")
            else:
                self.lbl_tx_status.setStyleSheet(
                    "color:#0a5a28; font-size:11px; font-weight:700;")
                self.tx_bar.setStyleSheet(
                    "background:#c8d6ec; border-bottom:1px solid #7a8aa0;")

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
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#1e1e2e;border:1px solid #45475a;border-radius:6px;padding:4px;}"
            "QMenu::item{padding:6px 20px 6px 12px;color:#cdd6f4;border-radius:4px;}"
            "QMenu::item:selected{background:#89b4fa;color:#1e1e2e;}"
            "QMenu::separator{height:1px;background:#45475a;margin:4px 8px;}")

        def add(label: str, sql: str):
            act = menu.addAction(label)
            act.triggered.connect(lambda: self.editor.insert_snippet(sql))

        table = self._current_table()

        menu.addSection("─── SELECT ───────────")
        add('SELECT * (100 linhas)',
            f'SELECT * FROM "{table}" LIMIT 100')
        add('SELECT com filtro',
            f'SELECT * FROM "{table}"\nWHERE COD_EMPRESA = \'001\'\nLIMIT 100')
        add('COUNT registros',
            f'SELECT COUNT(*) AS total FROM "{table}"')
        add('SELECT campos específicos',
            f'SELECT COD_EMPRESA, COD_ESTAB, DATA_FISCAL,\n'
            f'       NUM_DOCFIS, SERIE_DOCFIS\nFROM "{table}"\nLIMIT 100')
        add('GROUP BY empresa/estab',
            f'SELECT COD_EMPRESA, COD_ESTAB,\n'
            f'       COUNT(*) AS qtd\nFROM "{table}"\n'
            f'GROUP BY COD_EMPRESA, COD_ESTAB\nORDER BY COD_EMPRESA')

        menu.addSection("─── UPDATE ───────────")
        add('UPDATE campo único',
            f'UPDATE "{table}"\nSET CAMPO = \'NOVO_VALOR\'\n'
            f'WHERE COD_EMPRESA = \'001\'\n  AND NUM_DOCFIS = \'000001\'')
        add('UPDATE múltiplos campos',
            f'UPDATE "{table}"\nSET CAMPO1 = \'VALOR1\',\n'
            f'    CAMPO2 = \'VALOR2\'\nWHERE _row_id = 1')
        add('UPDATE com SELECT (verificar antes)',
            f'-- Primeiro verifique os registros:\nSELECT * FROM "{table}"\n'
            f'WHERE COD_EMPRESA = \'001\' LIMIT 10\n\n'
            f'-- Depois execute o UPDATE:\n-- UPDATE "{table}" SET CAMPO = \'VALOR\'\n'
            f'-- WHERE COD_EMPRESA = \'001\'')

        menu.addSection("─── TRANSAÇÃO ────────")
        add('BEGIN + UPDATE + COMMIT',
            f'BEGIN;\n\nUPDATE "{table}"\nSET CAMPO = \'VALOR\'\n'
            f'WHERE COD_EMPRESA = \'001\';\n\n-- Verifique o resultado:\n'
            f'SELECT * FROM "{table}" WHERE COD_EMPRESA = \'001\' LIMIT 5;\n\n'
            f'COMMIT;  -- ou ROLLBACK para desfazer')
        add('ROLLBACK (desfazer)',
            'ROLLBACK;')
        add('COMMIT (confirmar)',
            'COMMIT;')

        menu.addSection("─── DIAGNÓSTICO ──────")
        add('EXPLAIN QUERY PLAN',
            f'EXPLAIN QUERY PLAN\nSELECT * FROM "{table}" WHERE COD_EMPRESA = \'001\'')
        add('Informações da tabela',
            f'PRAGMA table_info("{table}")')
        add('Contar por status/campo',
            f'SELECT SITUACAO, COUNT(*) AS qtd\nFROM "{table}"\n'
            f'GROUP BY SITUACAO\nORDER BY qtd DESC')
        add('Duplicatas por chave',
            f'SELECT COD_EMPRESA, COD_ESTAB, NUM_DOCFIS,\n'
            f'       COUNT(*) AS qtd\nFROM "{table}"\n'
            f'GROUP BY COD_EMPRESA, COD_ESTAB, NUM_DOCFIS\n'
            f'HAVING COUNT(*) > 1')
        add('Valores nulos/vazios',
            f'SELECT * FROM "{table}"\n'
            f'WHERE COD_EMPRESA = \'\' OR COD_EMPRESA IS NULL\nLIMIT 100')

        menu.exec(self.btn_snippets.mapToGlobal(
            self.btn_snippets.rect().bottomLeft()))

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
        self._update_undo_sql_btn()
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
        """Atualiza combo de tabelas disponíveis (SAFX + externas importadas)."""
        current = self.combo_tables.currentText()
        self.combo_tables.blockSignals(True)
        self.combo_tables.clear()
        self.combo_tables.addItem("-- Tabela --")
        seen = set()
        for t in tables:
            self.combo_tables.addItem(t)
            seen.add(t)
            if t.startswith("📊 "):
                seen.add(t[2:].strip())
        if self.db is not None and hasattr(self.db, 'list_external_tables'):
            for ext in sorted(self.db.list_external_tables()):
                if ext in seen:
                    continue
                label = f"📊 {ext}"
                self.combo_tables.addItem(label)
                seen.add(ext)
                seen.add(label)
        # Restaura seleção anterior
        idx = self.combo_tables.findText(current)
        if idx >= 0:
            self.combo_tables.setCurrentIndex(idx)
        self.combo_tables.blockSignals(False)
        self.editor.set_database(self.db)

    def set_query(self, sql: str):
        self.editor.setPlainText(sql)
        self.editor.setFocus()

    def add_external_table(self, table_name: str, columns: List[str]):
        """
        Adiciona uma tabela externa importada ao combo de tabelas e insere
        um snippet de JOIN de exemplo no editor SQL.
        """
        disp = f"📊 {table_name}"
        already = False
        for i in range(self.combo_tables.count()):
            t = self.combo_tables.itemText(i).strip()
            if t == table_name or t == disp:
                already = True
                break
            if t.startswith("📊 ") and t[2:].strip() == table_name:
                already = True
                break
        if not already:
            self.combo_tables.addItem(disp)

        # Insere snippet de JOIN no editor (INNER JOIN + colunas comuns SAFX/externa)
        current_sql = self.editor.toPlainText().strip()
        safx_tables = list(self.db.loaded_tables.keys()) if hasattr(self.db, 'loaded_tables') else []
        safx_ex = safx_tables[0] if safx_tables else 'SAFX_TABELA'
        join_snippet = self.db.build_external_join_example_sql(
            safx_ex, table_name, columns)
        if not current_sql:
            self.editor.setPlainText(join_snippet.strip())
        else:
            self.editor.appendPlainText(join_snippet)
