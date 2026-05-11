"""
Aba de Regras SAFX — interface visual para criar e executar regras de transformação.

Layout:
  ┌────────────────────────────────────────────────────────────────────────┐
  │ [Tabela ▼]  ▶ Executar Regra  ▶ Executar Pacote  [status]            │
  ├──────────────────┬─────────────────────────────────────────────────────┤
  │ 📦 Pacotes       │ Nome: [___________]  Tipo: [___▼]   [✓ Habilitar] │
  │   ▼ Pacote 1    │                                                     │
  │     ● Regra A   │ ─ CONDIÇÕES ─────────────────────────────────────  │
  │     ● Regra B   │   Lógica: (● AND  ○ OR)                            │
  │ 📋 Avulsas       │   [Campo▼] [Operador▼] [Valor___________] [🗑]    │
  │   ● Regra C     │   + Adicionar Condição                             │
  │                  │                                                     │
  │ [+Regra][+Pacote]│ ─ AÇÕES ──────────────────────────────────────── │
  │ [🗑 Remover]     │   [Tipo▼] [Campo▼] [Valor/Fórmula___________] [🗑]│
  │                  │   + Adicionar Ação                                 │
  │                  │                                                     │
  │                  │ [▶ Testar Prévia]  [💾 Salvar]  [🗑 Excluir]      │
  └──────────────────┴─────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSortFilterProxyModel, QStringListModel, QThread, QObject
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFrame,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressDialog,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSplitter,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from core.rule_engine import (
    ACTION_TYPES, CONDITION_OPS, FORMAT_TYPES, RuleEngine,
    eval_formula,
)

logger = logging.getLogger(__name__)


# ─── Worker de execução em background ────────────────────────────────────────
class _RuleWorker(QObject):
    """Executa regras/pacotes em thread separada para não travar a UI."""
    finished = pyqtSignal(int, list)      # (linhas_modificadas, erros)
    pkg_finished = pyqtSignal(list)       # [(nome, n, erros), ...]

    def __init__(self, engine, db, table: str,
                 rule=None, pkg_id: str = ""):
        super().__init__()
        self._engine = engine
        self._db = db
        self._table = table
        self._rule = rule
        self._pkg_id = pkg_id

    def run_rule(self):
        try:
            n, errors = self._engine.execute_rule(self._rule, self._db, self._table)
        except Exception as exc:
            n, errors = 0, [f"Erro inesperado: {exc}"]
        self.finished.emit(n, errors)

    def run_package(self):
        try:
            results = self._engine.execute_package(self._pkg_id, self._db, self._table)
        except Exception as exc:
            results = [("pacote", 0, [f"Erro inesperado: {exc}"])]
        self.pkg_finished.emit(results)


# ── Paleta ─────────────────────────────────────────────────────────────────────
_DARK = "#1e1e2e"
_SURFACE = "#181825"
_OVERLAY = "#313244"
_BORDER = "#45475a"
_TEXT = "#cdd6f4"
_MUTED = "#6c7086"
_ACCENT = "#89b4fa"
_GREEN = "#a6e3a1"
_RED = "#f38ba8"
_YELLOW = "#f9e2af"
_PEACH = "#fab387"

_BTN_BASE = (
    "QPushButton{border-radius:5px;font-size:12px;font-weight:600;padding:4px 12px;}"
    "QPushButton:hover{filter:brightness(1.15);}"
    "QPushButton:disabled{opacity:0.4;}"
)


def _btn(text: str, color: str = _ACCENT, bg: str = _DARK, width: int = 0) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(
        _BTN_BASE +
        f"QPushButton{{color:{color};background:{bg};"
        f"border:1px solid {color};}}")
    if width:
        b.setFixedWidth(width)
    b.setFixedHeight(30)
    return b


def _combo(items: Optional[List[str]] = None) -> QComboBox:
    c = QComboBox()
    c.setFixedHeight(28)
    c.setStyleSheet(
        f"QComboBox{{background:{_OVERLAY};color:{_TEXT};border:1px solid {_BORDER};"
        f"border-radius:4px;padding:0 6px;font-size:12px;}}"
        f"QComboBox::drop-down{{border:none;}}"
        f"QComboBox QAbstractItemView{{background:{_SURFACE};color:{_TEXT};"
        f"selection-background-color:{_ACCENT};selection-color:{_DARK};}}")
    if items:
        c.addItems(items)
    return c


def _field_combo(items: Optional[List[str]] = None) -> QComboBox:
    """Combo editável com busca incremental ao digitar (filtra por contains)."""
    c = QComboBox()
    c.setEditable(True)
    c.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    c.setFixedHeight(28)
    c.setStyleSheet(
        f"QComboBox{{background:{_OVERLAY};color:{_TEXT};border:1px solid {_BORDER};"
        f"border-radius:4px;padding:0 6px;font-size:12px;}}"
        f"QComboBox::drop-down{{border:none;width:18px;}}"
        f"QComboBox QAbstractItemView{{background:{_SURFACE};color:{_TEXT};"
        f"selection-background-color:{_ACCENT};selection-color:{_DARK};"
        f"font-size:12px;min-width:160px;}}"
        f"QLineEdit{{background:{_OVERLAY};color:{_TEXT};border:none;"
        f"padding:0 4px;font-size:12px;}}")
    field_items = items or []
    c.addItems(field_items)

    # Completer com filtro "contains" (não só prefixo)
    completer = QCompleter(field_items, c)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    completer.popup().setStyleSheet(
        f"background:{_SURFACE};color:{_TEXT};font-size:12px;"
        f"selection-background-color:{_ACCENT};selection-color:{_DARK};")
    c.setCompleter(completer)
    return c


def _line(placeholder: str = "") -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(28)
    e.setStyleSheet(
        f"QLineEdit{{background:{_OVERLAY};color:{_TEXT};border:1px solid {_BORDER};"
        f"border-radius:4px;padding:0 6px;font-size:12px;}}")
    return e


def _lbl(text: str, color: str = _MUTED, bold: bool = False) -> QLabel:
    l = QLabel(text)
    w = "700" if bold else "400"
    l.setStyleSheet(f"color:{color};font-size:12px;font-weight:{w};")
    return l


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color:{_BORDER};background:{_BORDER};")
    f.setFixedHeight(1)
    return f


# ─── Widget de uma condição ────────────────────────────────────────────────────

class ConditionRow(QWidget):
    removed = pyqtSignal(object)

    def __init__(self, columns: List[str], parent=None):
        super().__init__(parent)
        self._columns = columns
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(4)

        self.combo_field = _field_combo(self._columns)
        self.combo_field.setMinimumWidth(140)
        lay.addWidget(self.combo_field)

        self.combo_op = _combo(list(CONDITION_OPS.values()))
        self.combo_op.setMinimumWidth(160)
        self.combo_op.currentIndexChanged.connect(self._on_op_changed)
        lay.addWidget(self.combo_op)

        self.edit_value = _line("valor ou {CAMPO}")
        self.edit_value.setMinimumWidth(140)
        lay.addWidget(self.edit_value, 1)

        btn_del = QToolButton()
        btn_del.setText("✕")
        btn_del.setFixedSize(26, 26)
        btn_del.setStyleSheet(
            f"QToolButton{{color:{_RED};background:{_DARK};"
            f"border:1px solid {_RED};border-radius:4px;font-weight:700;}}"
            f"QToolButton:hover{{background:#3a1a1a;}}")
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(btn_del)

    def _on_op_changed(self, idx: int):
        key = list(CONDITION_OPS.keys())[idx]
        self.edit_value.setEnabled(key not in ("is_empty", "is_not_empty"))

    def to_dict(self) -> Dict:
        op_key = list(CONDITION_OPS.keys())[self.combo_op.currentIndex()]
        return {
            "field": self.combo_field.currentText(),
            "op": op_key,
            "value": self.edit_value.text(),
        }

    def update_columns(self, columns: List[str]):
        """Atualiza o combo de campo com novas colunas, preservando valor atual."""
        self._columns = columns
        cur = self.combo_field.currentText()
        self.combo_field.blockSignals(True)
        self.combo_field.clear()
        self.combo_field.addItems(columns)
        self.combo_field.blockSignals(False)
        comp = self.combo_field.completer()
        if comp:
            from PyQt6.QtCore import QStringListModel
            comp.setModel(QStringListModel(columns, comp))
        idx = self.combo_field.findText(cur)
        if idx >= 0:
            self.combo_field.setCurrentIndex(idx)
        elif self.combo_field.isEditable():
            self.combo_field.setEditText(cur)

    def load_dict(self, d: Dict):
        col = d.get("field", "")
        idx = self.combo_field.findText(col)
        if idx >= 0:
            self.combo_field.setCurrentIndex(idx)
        elif self.combo_field.isEditable():
            self.combo_field.setEditText(col)

        op = d.get("op", "equals")
        op_keys = list(CONDITION_OPS.keys())
        if op in op_keys:
            self.combo_op.setCurrentIndex(op_keys.index(op))

        self.edit_value.setText(d.get("value", ""))


# ─── Widget de uma ação ───────────────────────────────────────────────────────

class ActionRow(QWidget):
    removed = pyqtSignal(object)

    def __init__(self, columns: List[str], db=None, parent=None):
        super().__init__(parent)
        self._columns = columns
        self._db = db
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(2)

        # Linha principal: tipo, campo, botão excluir
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self.combo_type = _combo(list(ACTION_TYPES.values()))
        self.combo_type.setMinimumWidth(200)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        row1.addWidget(self.combo_type)

        row1.addWidget(_lbl("→ campo:"))

        self.combo_field = _field_combo(self._columns)
        self.combo_field.setMinimumWidth(140)
        row1.addWidget(self.combo_field)

        btn_del = QToolButton()
        btn_del.setText("✕")
        btn_del.setFixedSize(26, 26)
        btn_del.setStyleSheet(
            f"QToolButton{{color:{_RED};background:{_DARK};"
            f"border:1px solid {_RED};border-radius:4px;font-weight:700;}}"
            f"QToolButton:hover{{background:#3a1a1a;}}")
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        row1.addWidget(btn_del)
        row1.addStretch()
        outer.addLayout(row1)

        # Linha de valor/fórmula (dinâmica por tipo)
        self._extra_widget = QWidget()
        self._extra_lay = QHBoxLayout(self._extra_widget)
        self._extra_lay.setContentsMargins(4, 0, 0, 0)
        self._extra_lay.setSpacing(4)
        outer.addWidget(self._extra_widget)

        self._build_value_widget()

    def _clear_extra(self):
        while self._extra_lay.count():
            item = self._extra_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_type_changed(self, _idx: int):
        self._build_value_widget()

    def _build_value_widget(self):
        self._clear_extra()
        atype = self._current_type()

        if atype == "set_value":
            self._extra_lay.addWidget(_lbl("Valor:"))
            self.w_value = _line("texto ou número")
            self._extra_lay.addWidget(self.w_value, 1)

        elif atype in ("set_formula", "concat"):
            self._extra_lay.addWidget(_lbl("Fórmula:"))
            self.w_formula = _line("{CAMPO1} * {CAMPO2}  ou  {NOME} + ' ' + {SOBRENOME}")
            self._extra_lay.addWidget(self.w_formula, 1)
            tip = _lbl("  Use {CAMPO} para referenciar campos", _MUTED)
            self._extra_lay.addWidget(tip)

        elif atype == "copy_field":
            self._extra_lay.addWidget(_lbl("De:"))
            self.w_source = _combo(self._columns)
            self._extra_lay.addWidget(self.w_source)

        elif atype == "table_lookup":
            self._build_table_lookup_widget()

        elif atype == "format":
            self._extra_lay.addWidget(_lbl("Formato:"))
            self.w_fmt = _combo(list(FORMAT_TYPES.values()))
            self.w_fmt.setMinimumWidth(200)
            self._extra_lay.addWidget(self.w_fmt)
            self._extra_lay.addWidget(_lbl("  Arg:"))
            self.w_fmt_arg = _line("ex: 10  ou  antigo|novo")
            self.w_fmt_arg.setFixedWidth(120)
            self._extra_lay.addWidget(self.w_fmt_arg)

        elif atype == "lookup":
            self._extra_lay.addWidget(_lbl("Mapeamento:"))
            self.w_mapping = _line("A=Aprovado; R=Reprovado; P=Pendente")
            self._extra_lay.addWidget(self.w_mapping, 1)

        elif atype == "conditional":
            self._extra_lay.addWidget(_lbl("Se:"))
            self.w_cond_formula = _line("{VALOR} > 0")
            self.w_cond_formula.setFixedWidth(150)
            self._extra_lay.addWidget(self.w_cond_formula)
            self._extra_lay.addWidget(_lbl("então:"))
            self.w_then = _line("SIM")
            self.w_then.setFixedWidth(80)
            self._extra_lay.addWidget(self.w_then)
            self._extra_lay.addWidget(_lbl("senão:"))
            self.w_else = _line("NÃO")
            self.w_else.setFixedWidth(80)
            self._extra_lay.addWidget(self.w_else)

        elif atype == "api_fetch":
            self._extra_lay.addWidget(_lbl("URL:"))
            self.w_url = _line("https://api.exemplo.com/dados/{CODIGO}")
            self._extra_lay.addWidget(self.w_url, 1)
            self._extra_lay.addWidget(_lbl("Campo resp.:"))
            self.w_resp = _line("data.valor")
            self.w_resp.setFixedWidth(120)
            self._extra_lay.addWidget(self.w_resp)

        self._extra_lay.addStretch()

    def _build_table_lookup_widget(self):
        """Constrói o widget de busca cross-table dinamicamente."""
        tables = self._db.get_loaded_tables() if self._db else []

        self._extra_lay.addWidget(_lbl("Tabela:"))
        self.w_src_table = _combo(tables)
        self.w_src_table.setMinimumWidth(130)
        self._extra_lay.addWidget(self.w_src_table)

        self._extra_lay.addWidget(_lbl(" Onde:"))
        self.w_src_match = _combo()
        self.w_src_match.setMinimumWidth(120)
        self._extra_lay.addWidget(self.w_src_match)

        self._extra_lay.addWidget(_lbl("="))
        self.w_local_match = _combo(self._columns)
        self.w_local_match.setMinimumWidth(110)
        self.w_local_match.setToolTip("Campo desta tabela cujo valor é usado como filtro")
        self._extra_lay.addWidget(self.w_local_match)

        self._extra_lay.addWidget(_lbl(" Retornar:"))
        self.w_ret_field = _combo()
        self.w_ret_field.setMinimumWidth(110)
        self._extra_lay.addWidget(self.w_ret_field)

        self._extra_lay.addWidget(_lbl(" Padrão:"))
        self.w_default = _line("")
        self.w_default.setFixedWidth(70)
        self._extra_lay.addWidget(self.w_default)

        # Quando troca a tabela-fonte, atualiza os combos de campo
        self.w_src_table.currentTextChanged.connect(self._on_src_table_changed)
        if tables:
            self._on_src_table_changed(tables[0])

    def _on_src_table_changed(self, table: str):
        if not self._db or not table:
            return
        cols = self._db.get_table_columns(table)
        for c in (getattr(self, "w_src_match", None),
                  getattr(self, "w_ret_field", None)):
            if c is not None:
                cur = c.currentText()
                c.clear()
                c.addItems(cols)
                idx = c.findText(cur)
                if idx >= 0:
                    c.setCurrentIndex(idx)

    @staticmethod
    def _refresh_field_combo(combo: QComboBox, columns: List[str]):
        """Atualiza items e completer de um _field_combo preservando valor atual."""
        cur = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(columns)
        combo.blockSignals(False)
        comp = combo.completer()
        if comp:
            comp.setModel(QStringListModel(columns, comp))
        idx = combo.findText(cur)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.isEditable():
            combo.setEditText(cur)

    def update_columns(self, columns: List[str]):
        """Atualiza todos os combos de campo desta linha quando a tabela muda."""
        self._columns = columns
        self._refresh_field_combo(self.combo_field, columns)

        # Atualiza combo de cópia de campo
        w_src = getattr(self, "w_source", None)
        if w_src is not None:
            self._refresh_field_combo(w_src, columns)

        # Atualiza campo local no table_lookup
        w_lm = getattr(self, "w_local_match", None)
        if w_lm is not None:
            self._refresh_field_combo(w_lm, columns)

    def _current_type(self) -> str:
        idx = self.combo_type.currentIndex()
        return list(ACTION_TYPES.keys())[idx]

    def to_dict(self) -> Dict:
        atype = self._current_type()
        d: Dict[str, Any] = {
            "type": atype,
            "field": self.combo_field.currentText(),
        }
        if atype == "set_value":
            d["value"] = getattr(self, "w_value", _line()).text()
        elif atype in ("set_formula", "concat"):
            d["formula"] = getattr(self, "w_formula", _line()).text()
        elif atype == "copy_field":
            src_w = getattr(self, "w_source", None)
            d["source_field"] = src_w.currentText() if src_w else ""
        elif atype == "format":
            fmt_keys = list(FORMAT_TYPES.keys())
            fidx = getattr(self, "w_fmt", _combo()).currentIndex()
            d["format_type"] = fmt_keys[fidx] if 0 <= fidx < len(fmt_keys) else "uppercase"
            d["format_arg"] = getattr(self, "w_fmt_arg", _line()).text()
        elif atype == "lookup":
            d["mapping_raw"] = getattr(self, "w_mapping", _line()).text()
        elif atype == "table_lookup":
            d["src_table"] = getattr(self, "w_src_table", _combo()).currentText()
            d["src_match_field"] = getattr(self, "w_src_match", _combo()).currentText()
            d["local_match_field"] = getattr(self, "w_local_match", _combo()).currentText()
            d["return_field"] = getattr(self, "w_ret_field", _combo()).currentText()
            d["default_value"] = getattr(self, "w_default", _line()).text()
            d["match_op"] = "equals"
        elif atype == "conditional":
            d["formula"] = getattr(self, "w_cond_formula", _line()).text()
            d["then_value"] = getattr(self, "w_then", _line()).text()
            d["else_value"] = getattr(self, "w_else", _line()).text()
        elif atype == "api_fetch":
            d["url"] = getattr(self, "w_url", _line()).text()
            d["response_field"] = getattr(self, "w_resp", _line()).text()
        return d

    def load_dict(self, d: Dict):
        atype = d.get("type", "set_value")
        keys = list(ACTION_TYPES.keys())
        if atype in keys:
            self.combo_type.setCurrentIndex(keys.index(atype))
            self._build_value_widget()

        col = d.get("field", "")
        idx = self.combo_field.findText(col)
        if idx >= 0:
            self.combo_field.setCurrentIndex(idx)

        if atype == "set_value":
            getattr(self, "w_value", _line()).setText(d.get("value", ""))
        elif atype in ("set_formula", "concat"):
            getattr(self, "w_formula", _line()).setText(d.get("formula", ""))
        elif atype == "copy_field":
            src = d.get("source_field", "")
            w = getattr(self, "w_source", None)
            if w:
                i = w.findText(src)
                if i >= 0:
                    w.setCurrentIndex(i)
        elif atype == "format":
            fmt_keys = list(FORMAT_TYPES.keys())
            ft = d.get("format_type", "uppercase")
            if ft in fmt_keys:
                getattr(self, "w_fmt", _combo()).setCurrentIndex(fmt_keys.index(ft))
            getattr(self, "w_fmt_arg", _line()).setText(d.get("format_arg", ""))
        elif atype == "lookup":
            getattr(self, "w_mapping", _line()).setText(d.get("mapping_raw", ""))
        elif atype == "conditional":
            getattr(self, "w_cond_formula", _line()).setText(d.get("formula", ""))
            getattr(self, "w_then", _line()).setText(d.get("then_value", ""))
            getattr(self, "w_else", _line()).setText(d.get("else_value", ""))
        elif atype == "api_fetch":
            getattr(self, "w_url", _line()).setText(d.get("url", ""))
            getattr(self, "w_resp", _line()).setText(d.get("response_field", ""))


# ─── Aba principal de Regras ──────────────────────────────────────────────────

class RulesTab(QWidget):
    """Aba de regras de transformação de dados."""

    # Emitido quando uma regra modifica dados — para recarregar a grade
    dataChanged = pyqtSignal()
    # Emitido quando o usuário muda a tabela pelo combo — sincroniza header principal
    tableActivated = pyqtSignal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.engine = RuleEngine()
        self._current_rule_id: Optional[str] = None
        self._current_pkg_id: Optional[str] = None
        self._columns: List[str] = []
        self._condition_rows: List[ConditionRow] = []
        self._action_rows: List[ActionRow] = []
        self._in_sync = False   # evita loop de sinalização
        self._active_thread = None  # ref para evitar GC da thread de execução
        self._active_worker = None
        self._build()

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setStyleSheet(f"background:{_DARK};color:{_TEXT};")

        # Barra de ferramentas superior
        self._toolbar_bar = self._build_toolbar()
        root.addWidget(self._toolbar_bar)
        root.addWidget(_sep())

        # Divisão esquerda (lista) / direita (editor)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet(
            f"QSplitter::handle{{background:{_BORDER};}}")

        self._left_panel = self._build_left_panel()
        self._right_scroll = self._build_right_panel()
        self._splitter.addWidget(self._left_panel)
        self._splitter.addWidget(self._right_scroll)
        self._splitter.setSizes([220, 700])

        root.addWidget(self._splitter, 1)

        # Barra de status
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet(
            f"background:{_SURFACE};color:{_MUTED};font-size:11px;padding:4px 12px;")
        self._lbl_status.setFixedHeight(24)
        root.addWidget(self._lbl_status)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"background:{_SURFACE};border-bottom:1px solid {_BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        lay.addWidget(_lbl("Tabela:", _MUTED))
        self._combo_table = _combo()
        self._combo_table.setMinimumWidth(180)
        self._combo_table.currentTextChanged.connect(self._on_table_changed)
        lay.addWidget(self._combo_table)

        lay.addWidget(_sep_v())

        self._btn_exec_rule = _btn("▶  Executar Regra", _GREEN, "#1a3a1a", 160)
        self._btn_exec_rule.clicked.connect(self._exec_current_rule)
        lay.addWidget(self._btn_exec_rule)

        self._btn_exec_pkg = _btn("▶▶  Executar Pacote", _PEACH, "#2a1a0a", 170)
        self._btn_exec_pkg.clicked.connect(self._exec_current_pkg)
        lay.addWidget(self._btn_exec_pkg)

        lay.addWidget(_sep_v())

        self._lbl_toolbar = QLabel("")
        self._lbl_toolbar.setStyleSheet(f"color:{_MUTED};font-size:11px;")
        lay.addWidget(self._lbl_toolbar)
        lay.addStretch()

        btn_ref = _btn("⟳ Atualizar", _MUTED, _DARK, 110)
        btn_ref.clicked.connect(self.refresh_tables)
        lay.addWidget(btn_ref)

        return bar

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        left.setMinimumWidth(190)
        left.setMaximumWidth(260)
        left.setStyleSheet(f"background:{_SURFACE};border-right:1px solid {_BORDER};")
        self._left_panel_ref = left
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        # Cabeçalho
        hdr = QWidget()
        hdr.setStyleSheet(f"background:{_OVERLAY};border-bottom:1px solid {_BORDER};")
        self._left_hdr = hdr
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(8, 6, 8, 6)
        self._lbl_rules_hdr = _lbl("📋  Regras & Pacotes", _ACCENT, True)
        hdr_lay.addWidget(self._lbl_rules_hdr)
        ll.addWidget(hdr)

        # Lista
        self._rule_list = QListWidget()
        self._rule_list.setStyleSheet(
            f"QListWidget{{background:{_SURFACE};border:none;color:{_TEXT};font-size:12px;}}"
            f"QListWidget::item{{padding:6px 10px;border-bottom:1px solid {_BORDER};}}"
            f"QListWidget::item:selected{{background:{_ACCENT};color:{_DARK};font-weight:700;}}")
        self._rule_list.currentItemChanged.connect(self._on_list_item_changed)
        ll.addWidget(self._rule_list, 1)

        # Botões
        btn_area = QWidget()
        btn_area.setStyleSheet(f"background:{_OVERLAY};border-top:1px solid {_BORDER};")
        self._left_btn_area = btn_area
        blay = QVBoxLayout(btn_area)
        blay.setContentsMargins(8, 6, 8, 6)
        blay.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(4)
        btn_add_rule = _btn("+ Regra", _GREEN, "#1a3a1a")
        btn_add_rule.clicked.connect(self._new_rule)
        row1.addWidget(btn_add_rule)
        btn_add_pkg = _btn("+ Pacote", _ACCENT, "#0a1a3a")
        btn_add_pkg.clicked.connect(self._new_package)
        row1.addWidget(btn_add_pkg)
        blay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        btn_add_to_pkg = _btn("↳ Adicionar ao Pacote", _YELLOW, "#2a1a00")
        btn_add_to_pkg.setFixedHeight(28)
        btn_add_to_pkg.clicked.connect(self._add_rule_to_package)
        row2.addWidget(btn_add_to_pkg)
        blay.addLayout(row2)

        btn_del = _btn("🗑  Remover", _RED, "#2a0a0a")
        btn_del.clicked.connect(self._delete_selected)
        blay.addWidget(btn_del)

        ll.addWidget(btn_area)
        return left

    def _build_right_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:{_DARK};}}")
        self._right_scroll_ref = scroll

        right = QWidget()
        right.setStyleSheet(f"background:{_DARK};")
        self._right_widget = right
        self._right_lay = QVBoxLayout(right)
        self._right_lay.setContentsMargins(16, 12, 16, 16)
        self._right_lay.setSpacing(12)

        # Placeholder
        self._placeholder = QLabel(
            "← Selecione uma regra ou clique em  + Regra  para começar")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color:{_MUTED};font-size:14px;padding:40px;")
        self._right_lay.addWidget(self._placeholder)

        # Editor (oculto inicialmente)
        self._editor = QWidget()
        ed_lay = QVBoxLayout(self._editor)
        ed_lay.setContentsMargins(0, 0, 0, 0)
        ed_lay.setSpacing(10)

        # ── Cabeçalho da regra ────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(_lbl("Nome:", _MUTED))
        self._edit_name = _line("Nome da regra")
        self._edit_name.setMinimumWidth(260)
        hdr_row.addWidget(self._edit_name, 1)
        self._chk_enabled = QCheckBox("Habilitada")
        self._chk_enabled.setChecked(True)
        self._chk_enabled.setStyleSheet(
            f"QCheckBox{{color:{_GREEN};font-size:12px;font-weight:700;}}"
            f"QCheckBox::indicator{{width:15px;height:15px;"
            f"border:2px solid {_GREEN};border-radius:3px;background:{_SURFACE};}}"
            f"QCheckBox::indicator:checked{{background:{_GREEN};}}")
        hdr_row.addWidget(self._chk_enabled)
        ed_lay.addLayout(hdr_row)

        # Descrição opcional
        desc_row = QHBoxLayout()
        desc_row.addWidget(_lbl("Desc:", _MUTED))
        self._edit_desc = _line("Descrição opcional da regra")
        desc_row.addWidget(self._edit_desc, 1)
        ed_lay.addLayout(desc_row)

        ed_lay.addWidget(_sep())

        # ── Condições ─────────────────────────────────────────────────────────
        cond_hdr = QHBoxLayout()
        cond_hdr.addWidget(_lbl("🔎  CONDIÇÕES", _ACCENT, True))
        cond_hdr.addWidget(_lbl(" (sem condições → aplica a todos os registros)", _MUTED))
        cond_hdr.addStretch()
        cond_hdr.addWidget(_lbl("Lógica:", _MUTED))
        self._rb_and = QRadioButton("AND")
        self._rb_or = QRadioButton("OR")
        self._rb_and.setChecked(True)
        for rb in (self._rb_and, self._rb_or):
            rb.setStyleSheet(f"QRadioButton{{color:{_TEXT};font-size:12px;}}")
        cond_hdr.addWidget(self._rb_and)
        cond_hdr.addWidget(self._rb_or)
        ed_lay.addLayout(cond_hdr)

        self._cond_container = QWidget()
        self._cond_lay = QVBoxLayout(self._cond_container)
        self._cond_lay.setContentsMargins(0, 0, 0, 0)
        self._cond_lay.setSpacing(2)
        ed_lay.addWidget(self._cond_container)

        btn_add_cond = _btn("+ Adicionar Condição", _MUTED, _DARK, 180)
        btn_add_cond.clicked.connect(lambda: self._add_condition_row())
        ed_lay.addWidget(btn_add_cond, alignment=Qt.AlignmentFlag.AlignLeft)

        ed_lay.addWidget(_sep())

        # ── Ações ─────────────────────────────────────────────────────────────
        act_hdr = QHBoxLayout()
        act_hdr.addWidget(_lbl("⚡  AÇÕES", _YELLOW, True))
        act_hdr.addStretch()
        self._lbl_fields_hint = _lbl("  Campos disponíveis carregam com a tabela", _MUTED)
        act_hdr.addWidget(self._lbl_fields_hint)
        ed_lay.addLayout(act_hdr)

        self._act_container = QWidget()
        self._act_lay = QVBoxLayout(self._act_container)
        self._act_lay.setContentsMargins(0, 0, 0, 0)
        self._act_lay.setSpacing(2)
        ed_lay.addWidget(self._act_container)

        btn_add_act = _btn("+ Adicionar Ação", _YELLOW, "#2a1a00", 160)
        btn_add_act.clicked.connect(lambda: self._add_action_row())
        ed_lay.addWidget(btn_add_act, alignment=Qt.AlignmentFlag.AlignLeft)

        ed_lay.addWidget(_sep())

        # ── Área de fórmula de ajuda ───────────────────────────────────────────
        help_gb = QGroupBox("📖  Ajuda rápida — Fórmulas & Referências")
        help_gb.setStyleSheet(
            f"QGroupBox{{color:{_MUTED};font-size:11px;font-weight:700;"
            f"border:1px solid {_BORDER};border-radius:5px;margin-top:6px;padding:10px 8px 6px 8px;}}"
            f"QGroupBox::title{{padding:0 4px;}}")
        self._help_gb = help_gb
        help_lay = QVBoxLayout(help_gb)
        help_lay.setSpacing(2)
        help_text = QLabel(
            "<b>Referências de campo:</b>  <code>{NOME_DO_CAMPO}</code>  ou  "
            "<code>NOME_DO_CAMPO</code> (sem espaços) em fórmulas<br>"
            "<b>Matemática:</b>  <code>{PRECO} * {QTDE}</code> &nbsp;&nbsp; "
            "<code>round({TOTAL} / 12, 2)</code> &nbsp;&nbsp; "
            "<code>sqrt({AREA})</code><br>"
            "<b>Texto:</b>  <code>{NOME} + ' ' + {SOBRENOME}</code> &nbsp;&nbsp; "
            "<code>str({CODIGO}).zfill(10)</code><br>"
            "<b>Condicional:</b>  <code>{VALOR} &gt; 0</code> → então <code>ATIVO</code> "
            "senão <code>INATIVO</code><br>"
            "<b>API:</b>  <code>https://api.exemplo.com/dados/{CODIGO}</code> &nbsp; "
            "campo resposta: <code>result.value</code>"
        )
        help_text.setTextFormat(Qt.TextFormat.RichText)
        help_text.setWordWrap(True)
        help_text.setStyleSheet(
            f"color:{_MUTED};font-size:11px;background:transparent;")
        self._help_text = help_text
        help_lay.addWidget(help_text)
        ed_lay.addWidget(help_gb)

        # ── Botões de ação ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_test = _btn("🔍  Testar Prévia", _ACCENT, "#0a1a3a", 160)
        btn_test.clicked.connect(self._preview_rule)
        btn_row.addWidget(btn_test)

        btn_save = _btn("💾  Salvar Regra", _GREEN, "#0a2a0a", 160)
        btn_save.clicked.connect(self._save_rule)
        btn_row.addWidget(btn_save)

        btn_del_rule = _btn("🗑  Excluir Regra", _RED, "#2a0a0a", 150)
        btn_del_rule.clicked.connect(self._delete_selected)
        btn_row.addWidget(btn_del_rule)

        btn_row.addStretch()
        ed_lay.addLayout(btn_row)

        self._editor.hide()
        self._right_lay.addWidget(self._editor)
        self._right_lay.addStretch()

        scroll.setWidget(right)
        return scroll

    # ── Tema ──────────────────────────────────────────────────────────────────

    def apply_theme(self, theme: str = 'dark'):
        """Propaga tema claro/escuro para TODOS os widgets da aba de Regras."""
        is_light = (theme == 'light')

        if is_light:
            bg       = '#f0f2f5'
            surface  = '#e8eaf0'
            overlay  = '#dde1ea'
            border   = '#b8bcd0'
            text     = '#1a1a2e'
            muted    = '#5a6070'
            accent   = '#1a5ab4'
            sel_text = 'white'
            input_bg = 'white'
        else:
            bg       = _DARK
            surface  = _SURFACE
            overlay  = _OVERLAY
            border   = _BORDER
            text     = _TEXT
            muted    = _MUTED
            accent   = _ACCENT
            sel_text = _DARK
            input_bg = _OVERLAY

        # ── 1. QSS base no root (cascata para filhos sem style próprio) ──────
        self.setStyleSheet(
            f"QWidget{{background:{bg};color:{text};}}"
            f"QRadioButton{{color:{text};}}"
            f"QCheckBox{{color:{text};}}"
            f"QSplitter::handle{{background:{border};}}"
        )

        # ── 2. Painéis estruturais (têm style inline próprio → atualizar) ────
        self._right_scroll_ref.setStyleSheet(
            f"QScrollArea{{border:none;background:{bg};}}")
        self._right_widget.setStyleSheet(f"background:{bg};")
        self._toolbar_bar.setStyleSheet(
            f"background:{surface};border-bottom:1px solid {border};")
        self._left_panel_ref.setStyleSheet(
            f"background:{surface};border-right:1px solid {border};")
        self._left_hdr.setStyleSheet(
            f"background:{overlay};border-bottom:1px solid {border};")
        self._left_btn_area.setStyleSheet(
            f"background:{overlay};border-top:1px solid {border};")
        self._lbl_status.setStyleSheet(
            f"background:{surface};color:{muted};font-size:11px;padding:4px 12px;")
        self._splitter.setStyleSheet(
            f"QSplitter::handle{{background:{border};}}")

        # ── 3. Labels de cabeçalho ────────────────────────────────────────────
        self._lbl_rules_hdr.setStyleSheet(
            f"color:{accent};font-size:12px;font-weight:700;")
        self._lbl_toolbar.setStyleSheet(
            f"color:{muted};font-size:11px;background:transparent;")

        # ── 4. Lista de regras ────────────────────────────────────────────────
        self._rule_list.setStyleSheet(
            f"QListWidget{{background:{surface};border:none;color:{text};font-size:12px;}}"
            f"QListWidget::item{{padding:6px 10px;border-bottom:1px solid {border};}}"
            f"QListWidget::item:selected{{background:{accent};color:{sel_text};font-weight:700;}}")

        # ── 5. Placeholder ────────────────────────────────────────────────────
        self._placeholder.setStyleSheet(
            f"color:{muted};font-size:14px;padding:40px;background:transparent;")

        # ── 6. Checkbox "Habilitada" ──────────────────────────────────────────
        self._chk_enabled.setStyleSheet(
            f"QCheckBox{{color:#28a745;font-size:12px;font-weight:700;background:transparent;}}"
            f"QCheckBox::indicator{{width:15px;height:15px;border:2px solid #28a745;"
            f"border-radius:3px;background:{input_bg};}}"
            f"QCheckBox::indicator:checked{{background:#28a745;}}")

        # ── 7. Radio buttons AND/OR ───────────────────────────────────────────
        for rb in (self._rb_and, self._rb_or):
            rb.setStyleSheet(f"QRadioButton{{color:{text};font-size:12px;background:transparent;}}")

        # ── 8. GroupBox de ajuda ──────────────────────────────────────────────
        self._help_gb.setStyleSheet(
            f"QGroupBox{{color:{muted};font-size:11px;font-weight:700;"
            f"border:1px solid {border};border-radius:5px;"
            f"margin-top:6px;padding:10px 8px 6px 8px;background:{bg};}}"
            f"QGroupBox::title{{padding:0 4px;background:{bg};}}")
        self._help_text.setStyleSheet(
            f"color:{muted};font-size:11px;background:transparent;")

        # ── 9. Hint de campos ─────────────────────────────────────────────────
        self._lbl_fields_hint.setStyleSheet(
            f"color:{muted};font-size:12px;background:transparent;")

        # ── 10. Todos os QLineEdit (exceto os internos ao QComboBox) ─────────
        combo_edits = {
            cb.lineEdit() for cb in self.findChildren(QComboBox)
            if cb.lineEdit() is not None
        }
        le_style = (
            f"QLineEdit{{background:{input_bg};color:{text};"
            f"border:1px solid {border};border-radius:4px;"
            f"padding:0 6px;font-size:12px;}}"
        )
        for le in self.findChildren(QLineEdit):
            if le not in combo_edits:
                le.setStyleSheet(le_style)

        # ── 11. Todos os QComboBox (incluindo field_combos com completer) ─────
        cb_style = (
            f"QComboBox{{background:{input_bg};color:{text};"
            f"border:1px solid {border};border-radius:4px;"
            f"padding:0 6px;font-size:12px;}}"
            f"QComboBox::drop-down{{border:none;width:18px;}}"
            f"QComboBox QAbstractItemView{{background:{input_bg};color:{text};"
            f"selection-background-color:{accent};selection-color:{sel_text};"
            f"font-size:12px;min-width:160px;}}"
            f"QLineEdit{{background:{input_bg};color:{text};"
            f"border:none;padding:0 4px;font-size:12px;}}"
        )
        for cb in self.findChildren(QComboBox):
            cb.setStyleSheet(cb_style)
            comp = cb.completer()
            if comp and comp.popup():
                comp.popup().setStyleSheet(
                    f"background:{input_bg};color:{text};font-size:12px;"
                    f"selection-background-color:{accent};"
                    f"selection-color:{sel_text};"
                )

        # ── 12. Separadores horizontais (QFrame HLine) ────────────────────────
        for fr in self.findChildren(QFrame):
            if fr.frameShape() == QFrame.Shape.HLine:
                fr.setStyleSheet(f"background:{border};color:{border};")

    # ── Atualização da lista de tabelas ───────────────────────────────────────

    def refresh_tables(self):
        """Recarrega lista de tabelas carregadas no banco (mantém seleção atual)."""
        tables = self.db.get_loaded_tables()
        self._combo_table.blockSignals(True)
        current = self._combo_table.currentText()
        self._combo_table.clear()
        self._combo_table.addItems(tables)
        if current in tables:
            self._combo_table.setCurrentText(current)
        elif tables:
            self._combo_table.setCurrentIndex(0)
        self._combo_table.blockSignals(False)
        if tables:
            self._on_table_changed(self._combo_table.currentText())
        self._refresh_rule_list()

    def set_active_table(self, table_name: str):
        """Sincroniza o combo de tabelas com a tabela selecionada na sidebar principal."""
        self._in_sync = True
        try:
            tables = self.db.get_loaded_tables()
            self._combo_table.blockSignals(True)
            self._combo_table.clear()
            self._combo_table.addItems(tables)
            if table_name in tables:
                self._combo_table.setCurrentText(table_name)
            elif tables:
                self._combo_table.setCurrentIndex(0)
            self._combo_table.blockSignals(False)
            selected = self._combo_table.currentText()
            if selected:
                self._on_table_changed(selected)
            self._refresh_rule_list()
        finally:
            self._in_sync = False

    def _on_table_changed(self, table: str):
        self._columns = self.db.get_table_columns(table) if table else []
        # Atualiza campos nas linhas de condição (com completer)
        for cr in self._condition_rows:
            cr.update_columns(self._columns)
        # Atualiza campos nas linhas de ação (incluindo combos aninhados)
        for ar in self._action_rows:
            ar.update_columns(self._columns)
        # Notifica o main_window para sincronizar header e sidebar
        # _in_sync evita loop quando main_window já iniciou a troca
        if not self._in_sync and table:
            self.tableActivated.emit(table)

    # ── Lista de regras / pacotes ─────────────────────────────────────────────

    def _refresh_rule_list(self):
        self._rule_list.clear()

        # Pacotes
        for pkg in self.engine.packages:
            it = QListWidgetItem(f"  📦  {pkg.get('name', '?')}")
            it.setData(Qt.ItemDataRole.UserRole, ("pkg", pkg.get("id")))
            it.setFont(QFont("", 12, QFont.Weight.Bold))
            it.setForeground(Qt.GlobalColor.white)
            self._rule_list.addItem(it)

            # Regras dentro do pacote
            for rule_id in pkg.get("rule_ids", []):
                rule = self.engine.get_rule(rule_id)
                if rule:
                    icon = "●" if rule.get("enabled", True) else "○"
                    it2 = QListWidgetItem(f"    {icon}  {rule.get('name', '?')}")
                    it2.setData(Qt.ItemDataRole.UserRole, ("rule", rule.get("id")))
                    it2.setForeground(Qt.GlobalColor.lightGray)
                    self._rule_list.addItem(it2)

        # Regras avulsas (não pertencentes a nenhum pacote)
        pkg_rule_ids = set()
        for pkg in self.engine.packages:
            pkg_rule_ids.update(pkg.get("rule_ids", []))

        standalone = [r for r in self.engine.rules
                      if r.get("id") not in pkg_rule_ids]
        if standalone:
            sep_it = QListWidgetItem("  📋  Regras Avulsas")
            sep_it.setData(Qt.ItemDataRole.UserRole, None)
            sep_it.setFlags(sep_it.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            sep_it.setFont(QFont("", 11, QFont.Weight.Bold))
            self._rule_list.addItem(sep_it)

            for rule in standalone:
                icon = "●" if rule.get("enabled", True) else "○"
                it = QListWidgetItem(f"    {icon}  {rule.get('name', '?')}")
                it.setData(Qt.ItemDataRole.UserRole, ("rule", rule.get("id")))
                it.setForeground(Qt.GlobalColor.lightGray)
                self._rule_list.addItem(it)

    def _on_list_item_changed(self, item: Optional[QListWidgetItem], _prev=None):
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, obj_id = data
        if kind == "rule":
            self._current_rule_id = obj_id
            self._current_pkg_id = None
            rule = self.engine.get_rule(obj_id)
            if rule:
                self._load_rule_into_editor(rule)
        elif kind == "pkg":
            self._current_pkg_id = obj_id
            self._current_rule_id = None
            self._show_package_info(obj_id)

    # ── Editor de regra ────────────────────────────────────────────────────────

    def _show_editor(self):
        self._placeholder.hide()
        self._editor.show()

    def _load_rule_into_editor(self, rule: Dict):
        self._show_editor()
        self._clear_conditions()
        self._clear_actions()

        self._edit_name.setText(rule.get("name", ""))
        self._edit_desc.setText(rule.get("description", ""))
        self._chk_enabled.setChecked(rule.get("enabled", True))
        logic = rule.get("condition_logic", "AND")
        self._rb_and.setChecked(logic == "AND")
        self._rb_or.setChecked(logic == "OR")

        for cond in rule.get("conditions", []):
            row = self._add_condition_row()
            row.load_dict(cond)

        for act in rule.get("actions", []):
            row = self._add_action_row()
            row.load_dict(act)

    def _show_package_info(self, pkg_id: str):
        """Mostra informações do pacote (sem editor de regra individual)."""
        pkg = self.engine.get_package(pkg_id)
        if not pkg:
            return
        self._placeholder.setText(
            f"📦  Pacote:  {pkg.get('name', '?')}\n\n"
            f"Contém {len(pkg.get('rule_ids', []))} regra(s).\n\n"
            f"Clique em  ▶▶ Executar Pacote  para executar todas as regras em sequência.\n"
            f"Selecione uma regra na lista para editá-la.")
        self._placeholder.show()
        self._editor.hide()

    def _collect_rule(self) -> Dict:
        return {
            "id": self._current_rule_id or str(uuid.uuid4()),
            "name": self._edit_name.text() or "Sem nome",
            "description": self._edit_desc.text(),
            "enabled": self._chk_enabled.isChecked(),
            "condition_logic": "OR" if self._rb_or.isChecked() else "AND",
            "conditions": [cr.to_dict() for cr in self._condition_rows],
            "actions": [ar.to_dict() for ar in self._action_rows],
        }

    # ── Condições ─────────────────────────────────────────────────────────────

    def _add_condition_row(self, data: Optional[Dict] = None) -> ConditionRow:
        row = ConditionRow(self._columns, self)
        row.removed.connect(self._remove_condition_row)
        self._cond_lay.addWidget(row)
        self._condition_rows.append(row)
        if data:
            row.load_dict(data)
        return row

    def _remove_condition_row(self, row: ConditionRow):
        self._condition_rows.remove(row)
        self._cond_lay.removeWidget(row)
        row.deleteLater()

    def _clear_conditions(self):
        for row in list(self._condition_rows):
            self._cond_lay.removeWidget(row)
            row.deleteLater()
        self._condition_rows.clear()

    # ── Ações ──────────────────────────────────────────────────────────────────

    def _add_action_row(self, data: Optional[Dict] = None) -> ActionRow:
        row = ActionRow(self._columns, db=self.db, parent=self)
        row.removed.connect(self._remove_action_row)
        self._act_lay.addWidget(row)
        self._action_rows.append(row)
        if data:
            row.load_dict(data)
        return row

    def _remove_action_row(self, row: ActionRow):
        self._action_rows.remove(row)
        self._act_lay.removeWidget(row)
        row.deleteLater()

    def _clear_actions(self):
        for row in list(self._action_rows):
            self._act_lay.removeWidget(row)
            row.deleteLater()
        self._action_rows.clear()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _new_rule(self):
        self._current_rule_id = None
        self._current_pkg_id = None
        self._clear_conditions()
        self._clear_actions()
        self._edit_name.setText("")
        self._edit_desc.setText("")
        self._chk_enabled.setChecked(True)
        self._rb_and.setChecked(True)
        self._show_editor()
        self._edit_name.setFocus()
        self._set_status("Nova regra — configure as condições e ações, depois clique em 💾 Salvar.")

    def _new_package(self):
        name, ok = QInputDialog.getText(self, "Novo Pacote", "Nome do pacote:")
        if ok and name.strip():
            pkg = {"name": name.strip(), "rule_ids": [], "stop_on_error": False}
            self.engine.upsert_package(pkg)
            self._refresh_rule_list()
            self._set_status(f"Pacote '{name}' criado.")

    def _add_rule_to_package(self):
        pkgs = self.engine.packages
        if not pkgs:
            self._set_status("Crie um pacote primeiro (botão '+ Pacote').", error=True)
            return

        # Se um PACOTE está selecionado → pergunta qual regra adicionar a ELE
        if self._current_pkg_id and not self._current_rule_id:
            pkg = self.engine.get_package(self._current_pkg_id)
            if not pkg:
                return
            # Lista de regras ainda não neste pacote
            pkg_rule_ids = set(pkg.get("rule_ids", []))
            avail = [r for r in self.engine.rules
                     if r.get("id") not in pkg_rule_ids]
            if not avail:
                self._set_status("Todas as regras já estão neste pacote.", error=True)
                return
            rule_names = [r.get("name", "?") for r in avail]
            rname, ok = QInputDialog.getItem(
                self, "Adicionar Regra ao Pacote",
                f"Qual regra adicionar ao pacote  '{pkg.get('name','?')}'?",
                rule_names, 0, False)
            if not ok:
                return
            rule = avail[rule_names.index(rname)]
            pkg.get("rule_ids", []).append(rule.get("id"))
            pkg["rule_ids"] = pkg.get("rule_ids", [])
            self.engine.upsert_package(pkg)
            self._refresh_rule_list()
            self._set_status(
                f"✔ Regra '{rule.get('name')}' adicionada ao pacote '{pkg.get('name')}'.")
            return

        # Se uma REGRA está selecionada → pergunta em qual pacote colocar
        if not self._current_rule_id:
            self._set_status(
                "Selecione uma regra ou pacote na lista primeiro.", error=True)
            return

        pkg_names = [p.get("name", "?") for p in pkgs]
        name, ok = QInputDialog.getItem(
            self, "Adicionar ao Pacote", "Escolha o pacote:", pkg_names, 0, False)
        if not ok:
            return
        pkg = pkgs[pkg_names.index(name)]
        rule_ids = pkg.get("rule_ids", [])
        if self._current_rule_id not in rule_ids:
            rule_ids.append(self._current_rule_id)
            pkg["rule_ids"] = rule_ids
            self.engine.upsert_package(pkg)
            self._refresh_rule_list()
            self._set_status(f"✔ Regra adicionada ao pacote '{name}'.")
        else:
            self._set_status(f"Regra já está no pacote '{name}'.")

    def _save_rule(self):
        rule = self._collect_rule()
        if not rule["name"].strip() or rule["name"] == "Sem nome":
            self._set_status("Informe um nome para a regra.", error=True)
            return
        if not rule["actions"]:
            self._set_status("Adicione ao menos uma ação.", error=True)
            return
        self._current_rule_id = self.engine.upsert_rule(rule)
        self._refresh_rule_list()
        self._set_status(f"✔ Regra '{rule['name']}' salva.")

    def _delete_selected(self):
        item = self._rule_list.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, obj_id = data
        name = item.text().strip()
        r = QMessageBox.question(self, "Remover", f"Remover '{name}'?")
        if r != QMessageBox.StandardButton.Yes:
            return
        if kind == "rule":
            self.engine.delete_rule(obj_id)
        elif kind == "pkg":
            self.engine.delete_package(obj_id)
        self._current_rule_id = None
        self._current_pkg_id = None
        self._placeholder.setText(
            "← Selecione uma regra ou clique em  + Regra  para começar")
        self._placeholder.show()
        self._editor.hide()
        self._refresh_rule_list()

    # ── Execução ──────────────────────────────────────────────────────────────

    def _get_table(self) -> Optional[str]:
        table = self._combo_table.currentText()
        if not table:
            self._set_status("Nenhuma tabela selecionada — carregue um arquivo primeiro.", error=True)
            return None
        if table not in self.db.get_loaded_tables():
            self._set_status(f"Tabela '{table}' não está carregada.", error=True)
            return None
        return table

    def _exec_current_rule(self):
        table = self._get_table()
        if not table:
            return
        if not self._current_rule_id:
            self._set_status("Selecione uma regra para executar.", error=True)
            return
        rule = self.engine.get_rule(self._current_rule_id)
        if not rule:
            return
        confirm = QMessageBox.question(
            self, "Executar Regra",
            f"Executar a regra  '{rule.get('name')}'  sobre a tabela  '{table}'?\n\n"
            f"Esta operação modificará os dados na memória.")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._run_in_thread(rule=rule, table=table, mode="rule")

    def _exec_current_pkg(self):
        table = self._get_table()
        if not table:
            return
        if not self._current_pkg_id:
            self._set_status("Selecione um pacote para executar.", error=True)
            return
        pkg = self.engine.get_package(self._current_pkg_id)
        if not pkg:
            return
        confirm = QMessageBox.question(
            self, "Executar Pacote",
            f"Executar o pacote  '{pkg.get('name')}'  sobre a tabela  '{table}'?\n\n"
            f"As regras serão executadas em sequência.")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._run_in_thread(pkg_id=self._current_pkg_id, pkg_name=pkg.get("name", "?"),
                            table=table, mode="package")

    def _run_in_thread(self, table: str, mode: str,
                       rule=None, pkg_id: str = "", pkg_name: str = ""):
        """Executa regra ou pacote em QThread para não congelar a UI."""
        prog = QProgressDialog(
            "Executando regra, aguarde...", None, 0, 0, self)
        prog.setWindowTitle("Processando")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(400)
        prog.setValue(0)

        worker = _RuleWorker(self.engine, self.db, table,
                             rule=rule, pkg_id=pkg_id)
        thread = QThread(self)
        worker.moveToThread(thread)

        if mode == "rule":
            thread.started.connect(worker.run_rule)

            def _on_rule_done(n: int, errors: list):
                prog.close()
                thread.quit()
                self._show_exec_result(rule.get("name", "?"), n, errors)
                if n > 0:
                    self.dataChanged.emit()

            worker.finished.connect(_on_rule_done)
        else:
            thread.started.connect(worker.run_package)

            def _on_pkg_done(results: list):
                prog.close()
                thread.quit()
                total = sum(n for _, n, _ in results)
                all_errors: list = []
                lines: list = []
                for rname, n, errs in results:
                    lines.append(f"• {rname}: {n} linha(s) modificada(s)")
                    all_errors.extend(errs)
                summary = "\n".join(lines) or "Nenhuma regra executada."
                if all_errors:
                    summary += "\n\nErros:\n" + "\n".join(all_errors[:10])
                QMessageBox.information(
                    self, "Resultado do Pacote",
                    f"Pacote: {pkg_name}\nTabela: {table}\n\n"
                    f"Total: {total} linha(s) modificada(s)\n\n{summary}")
                if total > 0:
                    self.dataChanged.emit()

            worker.pkg_finished.connect(_on_pkg_done)

        # Limpeza ao terminar thread
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Guarda referências para evitar garbage collection
        self._active_thread = thread
        self._active_worker = worker

        thread.start()

    def _preview_rule(self):
        """Executa a regra em modo preview (só retorna amostra sem gravar)."""
        table = self._get_table()
        if not table:
            return
        rule = self._collect_rule()
        if not rule["actions"]:
            self._set_status("Adicione ao menos uma ação para prévia.", error=True)
            return

        from core.rule_engine import evaluate_conditions, check_condition
        try:
            with self.db._lock:
                cur = self.db.conn.cursor()
                cur.execute(f'SELECT * FROM "{table}" LIMIT 500')
                cols = [d[0] for d in cur.description]
                rows_data = cur.fetchall()
        except Exception as exc:
            self._set_status(f"Erro ao ler tabela: {exc}", error=True)
            return

        matches = []
        non_matches_sample = []
        conditions = rule.get("conditions", [])
        logic = rule.get("condition_logic", "AND")
        for rt in rows_data:
            row = dict(zip(cols, rt))
            if evaluate_conditions(conditions, logic, row):
                matches.append(row)
            elif len(non_matches_sample) < 3:
                non_matches_sample.append(row)

        # Monta debug: mostra valores reais dos campos das condições
        debug_lines = []
        if not matches and conditions:
            debug_lines.append("⚠  Nenhum registro correspondeu.\n")
            debug_lines.append("── Condições configuradas ──")
            for c in conditions:
                debug_lines.append(
                    f"  Campo: {c.get('field','')}  |  Operador: {c.get('op','')}  |  "
                    f"Valor buscado: '{c.get('value','')}'")
            debug_lines.append("")
            debug_lines.append("── Valores reais nos primeiros registros ──")
            cond_fields = [c.get("field","") for c in conditions if c.get("field")]
            for row in (non_matches_sample or []):
                parts = [f"{f}='{row.get(f,'')}'" for f in cond_fields]
                debug_lines.append("  " + "  |  ".join(parts))
            # Sugere campos que contêm o valor procurado
            debug_lines.append("")
            debug_lines.append("── Dica: campos que contêm os valores buscados ──")
            for cond in conditions:
                sought = str(cond.get("value", "")).strip()
                fname = cond.get("field", "")
                if sought and non_matches_sample:
                    found_in = []
                    for row in non_matches_sample[:1]:
                        for k, v in row.items():
                            if str(v).strip().lower() == sought.lower():
                                found_in.append(k)
                    if found_in:
                        debug_lines.append(
                            f"  ✔ Valor '{sought}' encontrado no(s) campo(s): "
                            f"{', '.join(found_in)}")
                    else:
                        debug_lines.append(
                            f"  ✗ Valor '{sought}' (campo '{fname}') não encontrado em nenhum campo do registro")

        dlg = PreviewDialog(matches[:20], rule, self._columns, self,
                            debug_info="\n".join(debug_lines))
        dlg.exec()

    def _show_exec_result(self, rule_name: str, modified: int, errors: List[str]):
        if errors:
            msg = (f"Regra: {rule_name}\n{modified} linha(s) modificada(s)\n\n"
                   f"Avisos/Erros:\n" + "\n".join(errors[:15]))
            QMessageBox.warning(self, "Execução concluída com avisos", msg)
        else:
            QMessageBox.information(
                self, "Execução concluída",
                f"Regra: {rule_name}\n✔  {modified} linha(s) modificada(s).")
        self._set_status(f"✔ {modified} linha(s) modificada(s) pela regra '{rule_name}'.")

    def _set_status(self, msg: str, error: bool = False):
        color = _RED if error else _MUTED
        self._lbl_status.setStyleSheet(
            f"background:{_SURFACE};color:{color};font-size:11px;padding:4px 12px;")
        self._lbl_status.setText(msg)


# ─── Separador vertical ────────────────────────────────────────────────────────

def _sep_v() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet(f"color:{_BORDER};background:{_BORDER};")
    f.setFixedWidth(1)
    return f


# ─── Diálogo de Prévia ─────────────────────────────────────────────────────────

class PreviewDialog(QDialog):
    """Mostra uma amostra dos registros que serão afetados pela regra."""

    def __init__(self, matching_rows: List[Dict], rule: Dict,
                 columns: List[str], parent=None, debug_info: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Prévia da Regra")
        self.setMinimumSize(760, 540)
        self.setStyleSheet(f"background:{_DARK};color:{_TEXT};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        count_color = _GREEN if matching_rows else _RED
        info = QLabel(
            f"<span style='color:{count_color};font-size:14px;font-weight:700;'>"
            f"{len(matching_rows)}</span> registro(s) serão afetados "
            f"(amostra de até 20).<br>"
            f"<span style='color:{_MUTED};font-size:11px;'>"
            f"Os valores abaixo mostram o resultado <i>simulado</i> — "
            f"nada foi gravado ainda.</span>")
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        lay.addWidget(info)

        # Debug info quando não há matches
        if debug_info:
            dbg = QTextEdit()
            dbg.setReadOnly(True)
            dbg.setMaximumHeight(130)
            dbg.setPlainText(debug_info)
            dbg.setStyleSheet(
                f"QTextEdit{{background:#2a1a00;color:{_YELLOW};"
                f"border:1px solid #6a4a00;border-radius:5px;"
                f"font-family:monospace;font-size:11px;padding:4px;}}")
            lay.addWidget(dbg)

        # Aplica ações simuladas
        from core.rule_engine import RuleEngine
        _eng = RuleEngine.__new__(RuleEngine)
        _eng._rules = []
        _eng._packages = []
        previews = []
        for row in matching_rows:
            sim = dict(row)
            for action in rule.get("actions", []):
                field = action.get("field", "")
                if field:
                    try:
                        val = _eng._apply_action(
                            action.get("type", "set_value"), action, field, sim, [])
                        if val is not None:
                            sim[field] = val
                    except Exception:
                        pass
            previews.append((row, sim))

        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(
            f"QTextEdit{{background:{_SURFACE};color:{_TEXT};"
            f"border:1px solid {_BORDER};border-radius:5px;"
            f"font-family:monospace;font-size:11px;padding:6px;}}")

        lines = []
        action_fields = [a.get("field", "") for a in rule.get("actions", [])]
        for orig, sim in previews:
            parts = []
            for f in action_fields:
                ov = str(orig.get(f, ""))
                nv = str(sim.get(f, ""))
                arrow = " → " if ov != nv else " = "
                parts.append(f"{f}: '{ov}'{arrow}'{nv}'")
            if parts:
                lines.append("  |  ".join(parts))

        if not lines and matching_rows:
            lines.append("(Valores já iguais ao resultado da ação — sem diferença visual)")

        text.setPlainText("\n".join(lines) if lines else "")
        lay.addWidget(text, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.setStyleSheet(f"color:{_TEXT};")
        lay.addWidget(btns)
