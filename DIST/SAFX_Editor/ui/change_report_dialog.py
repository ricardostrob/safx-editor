"""
Diálogo de Relatório de Alterações — mostra tudo que foi editado e confirmado.
"""
import os
import csv
import tempfile
from typing import List, Dict

from PyQt6.QtCore import Qt, QSortFilterProxyModel, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QColor, QFont, QBrush
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QHeaderView, QComboBox, QLineEdit, QWidget,
    QMessageBox, QFileDialog, QFrame, QApplication, QSplitter,
    QTextEdit, QSizePolicy
)

from core.database import SAFXDatabase


# ─── Model ────────────────────────────────────────────────────────────────────

_COLUMNS = ['Horário', 'Tabela', 'Row ID', 'Campo', 'Valor Anterior', 'Valor Novo', 'Origem']
_KEYS     = ['timestamp', 'table', 'row_id', 'field', 'old_value', 'new_value', 'source']


class ChangeLogModel(QAbstractTableModel):
    def __init__(self, data: List[Dict], parent=None):
        super().__init__(parent)
        self._data = data

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return _COLUMNS[section]
            return str(section + 1)
        if role == Qt.ItemDataRole.FontRole:
            f = QFont()
            f.setBold(True)
            f.setPointSize(11)
            return f
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._data[index.row()]
        key = _KEYS[index.column()]
        val = row.get(key, '')

        if role == Qt.ItemDataRole.DisplayRole:
            return str(val)

        if role == Qt.ItemDataRole.BackgroundRole:
            source = row.get('source', '')
            if source == 'sql':
                return QBrush(QColor("#1a1000"))
            if source == 'sql-result':
                return QBrush(QColor("#001a1a"))
            return QBrush(QColor("#0d1a0d"))

        if role == Qt.ItemDataRole.ForegroundRole:
            if key == 'new_value':
                return QBrush(QColor("#a6e3a1"))
            if key == 'old_value':
                return QBrush(QColor("#f38ba8"))
            if key == 'field':
                return QBrush(QColor("#89b4fa"))
            if key == 'table':
                return QBrush(QColor("#cba6f7"))
            return QBrush(QColor("#cdd6f4"))

        if role == Qt.ItemDataRole.FontRole:
            f = QFont("Consolas", 11)
            return f

        if role == Qt.ItemDataRole.ToolTipRole:
            return (
                f"Tabela: {row.get('table','')}\n"
                f"Row ID: {row.get('row_id','')}\n"
                f"Campo: {row.get('field','')}\n"
                f"Antes: {row.get('old_value','')}\n"
                f"Depois: {row.get('new_value','')}\n"
                f"Origem: {row.get('source','')}\n"
                f"Horário: {row.get('timestamp','')}"
            )

        return None


# ─── Dialog ───────────────────────────────────────────────────────────────────

class ChangeReportDialog(QDialog):
    """
    Relatório completo de todas as alterações realizadas e confirmadas na sessão.
    """

    def __init__(self, db: SAFXDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("📋  Relatório de Alterações — SAFX Editor")
        self.setMinimumSize(1100, 650)
        self.resize(1200, 720)

        self._all_data: List[Dict] = []
        self._filtered_data: List[Dict] = []

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        from ui.styles import MAIN_STYLE
        self.setStyleSheet(MAIN_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #0e1b2e, stop:1 #1a2e1a);"
            "border-bottom: 2px solid #313244;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 8, 20, 8)

        lbl_title = QLabel("📋  Relatório de Alterações da Sessão")
        lbl_title.setStyleSheet(
            "color: #a6e3a1; font-size: 16px; font-weight: 800; letter-spacing: 0.5px;")
        h_lay.addWidget(lbl_title)

        h_lay.addStretch()

        self.lbl_count = QLabel("0 alteração(ões)")
        self.lbl_count.setStyleSheet(
            "color: #89b4fa; font-size: 13px; font-weight: 600;")
        h_lay.addWidget(self.lbl_count)

        layout.addWidget(header)

        # ── Barra de filtros ──
        filter_bar = QWidget()
        filter_bar.setFixedHeight(46)
        filter_bar.setStyleSheet(
            "background:#181825; border-bottom:1px solid #313244;")
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(12, 6, 12, 6)
        fb_lay.setSpacing(8)

        lbl_f = QLabel("Filtrar:")
        lbl_f.setStyleSheet("color:#a6adc8; font-size:12px; font-weight:700;")
        fb_lay.addWidget(lbl_f)

        lbl_table = QLabel("Tabela:")
        lbl_table.setStyleSheet("color:#6c7086; font-size:12px;")
        fb_lay.addWidget(lbl_table)

        self.combo_table = QComboBox()
        self.combo_table.setFixedWidth(140)
        self.combo_table.setFixedHeight(30)
        self.combo_table.currentTextChanged.connect(self._apply_filter)
        fb_lay.addWidget(self.combo_table)

        lbl_origin = QLabel("Origem:")
        lbl_origin.setStyleSheet("color:#6c7086; font-size:12px;")
        fb_lay.addWidget(lbl_origin)

        self.combo_origin = QComboBox()
        self.combo_origin.setFixedWidth(120)
        self.combo_origin.setFixedHeight(30)
        self.combo_origin.addItems(["Todas", "manual", "sql", "sql-result"])
        self.combo_origin.currentTextChanged.connect(self._apply_filter)
        fb_lay.addWidget(self.combo_origin)

        lbl_search = QLabel("Buscar:")
        lbl_search.setStyleSheet("color:#6c7086; font-size:12px;")
        fb_lay.addWidget(lbl_search)

        self.search_edit = QLineEdit()
        self.search_edit.setFixedHeight(30)
        self.search_edit.setFixedWidth(240)
        self.search_edit.setPlaceholderText("campo, valor, row_id...")
        self.search_edit.setStyleSheet("font-size:12px; padding:2px 8px;")
        self.search_edit.textChanged.connect(self._apply_filter)
        fb_lay.addWidget(self.search_edit)

        fb_lay.addStretch()

        btn_refresh = QPushButton("🔄 Atualizar")
        btn_refresh.setFixedHeight(30)
        btn_refresh.setFixedWidth(100)
        btn_refresh.clicked.connect(self._load_data)
        fb_lay.addWidget(btn_refresh)

        layout.addWidget(filter_bar)

        # ── Tabela principal ──
        self.model = ChangeLogModel([], self)

        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.setAlternatingRowColors(False)
        self.table_view.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSortingEnabled(False)
        self.table_view.verticalHeader().setDefaultSectionSize(26)
        self.table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setEditTriggers(
            QTableView.EditTrigger.NoEditTriggers)

        layout.addWidget(self.table_view, 1)

        # ── Sumário ──
        summary_widget = QWidget()
        summary_widget.setFixedHeight(60)
        summary_widget.setStyleSheet(
            "background:#13131f; border-top:2px solid #313244;")
        s_lay = QHBoxLayout(summary_widget)
        s_lay.setContentsMargins(16, 8, 16, 8)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(
            "color:#a6adc8; font-size:12px; font-family:Consolas;")
        self.lbl_summary.setWordWrap(True)
        s_lay.addWidget(self.lbl_summary, 1)

        layout.addWidget(summary_widget)

        # ── Botões inferiores ──
        btn_bar = QWidget()
        btn_bar.setFixedHeight(52)
        btn_bar.setStyleSheet(
            "background:#181825; border-top:1px solid #313244;")
        b_lay = QHBoxLayout(btn_bar)
        b_lay.setContentsMargins(12, 8, 12, 8)
        b_lay.setSpacing(8)

        btn_export_csv = QPushButton("📥 Exportar CSV")
        btn_export_csv.setFixedHeight(34)
        btn_export_csv.setFixedWidth(140)
        btn_export_csv.setProperty("class", "primary")
        btn_export_csv.clicked.connect(self._export_csv)
        b_lay.addWidget(btn_export_csv)

        btn_copy = QPushButton("📋 Copiar Tudo")
        btn_copy.setFixedHeight(34)
        btn_copy.setFixedWidth(130)
        btn_copy.clicked.connect(self._copy_all)
        b_lay.addWidget(btn_copy)

        b_lay.addStretch()

        btn_clear = QPushButton("🗑 Limpar Log")
        btn_clear.setFixedHeight(34)
        btn_clear.setFixedWidth(120)
        btn_clear.setStyleSheet(
            "QPushButton{background:#3a1010;color:#f38ba8;"
            "border:1px solid #f38ba8;border-radius:6px;font-weight:700;}"
            "QPushButton:hover{background:#5a2020;}")
        btn_clear.clicked.connect(self._clear_log)
        b_lay.addWidget(btn_clear)

        btn_close = QPushButton("Fechar")
        btn_close.setFixedHeight(34)
        btn_close.setFixedWidth(90)
        btn_close.clicked.connect(self.accept)
        b_lay.addWidget(btn_close)

        layout.addWidget(btn_bar)

    # ─── Dados ────────────────────────────────────────────────────────────────

    def _load_data(self):
        self._all_data = self.db.get_change_log()

        # Popula combo de tabelas
        tables = sorted({d.get('table', '') for d in self._all_data if d.get('table')})
        current_table = self.combo_table.currentText()
        self.combo_table.blockSignals(True)
        self.combo_table.clear()
        self.combo_table.addItem("Todas")
        for t in tables:
            self.combo_table.addItem(t)
        idx = self.combo_table.findText(current_table)
        self.combo_table.setCurrentIndex(max(0, idx))
        self.combo_table.blockSignals(False)

        self._apply_filter()

    def _apply_filter(self):
        table_f = self.combo_table.currentText()
        origin_f = self.combo_origin.currentText()
        search_f = self.search_edit.text().lower().strip()

        filtered = []
        for row in self._all_data:
            if table_f != "Todas" and row.get('table') != table_f:
                continue
            if origin_f != "Todas" and row.get('source') != origin_f:
                continue
            if search_f:
                haystack = ' '.join(str(v).lower() for v in row.values())
                if search_f not in haystack:
                    continue
            filtered.append(row)

        self._filtered_data = filtered

        # Reconstrói o model
        self.model = ChangeLogModel(filtered, self)
        self.table_view.setModel(self.model)

        # Ajusta larguras
        widths = [140, 100, 65, 140, 160, 160, 80]
        for i, w in enumerate(widths):
            if i < self.model.columnCount():
                self.table_view.setColumnWidth(i, w)

        # Atualiza contadores e sumário
        total = len(self._all_data)
        showing = len(filtered)
        self.lbl_count.setText(
            f"{total} total | {showing} exibido(s)")

        self._update_summary(filtered)

    def _update_summary(self, data: List[Dict]):
        if not data:
            self.lbl_summary.setText("Nenhuma alteração registrada nesta sessão.")
            return

        by_table: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        for d in data:
            t = d.get('table', '?')
            s = d.get('source', '?')
            by_table[t] = by_table.get(t, 0) + 1
            by_source[s] = by_source.get(s, 0) + 1

        table_parts = [f"{t}: {n}" for t, n in sorted(by_table.items())]
        origin_parts = [f"{s}: {n}" for s, n in sorted(by_source.items())]

        self.lbl_summary.setText(
            f"Por tabela — {' | '.join(table_parts)}    "
            f"  Por origem — {' | '.join(origin_parts)}")

    # ─── Ações ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._filtered_data:
            QMessageBox.information(self, "Vazio", "Nenhuma alteração para exportar.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Relatório",
            "relatorio_alteracoes.csv",
            "CSV (*.csv);;Todos (*)")
        if not path:
            return

        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(
                    f, fieldnames=_KEYS,
                    extrasaction='ignore', delimiter=';')
                writer.writeheader()
                writer.writerows(self._filtered_data)

            QMessageBox.information(
                self, "Exportado",
                f"Relatório exportado com sucesso!\n\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar:\n{e}")

    def _copy_all(self):
        if not self._filtered_data:
            return
        lines = ['\t'.join(_COLUMNS)]
        for row in self._filtered_data:
            lines.append('\t'.join(str(row.get(k, '')) for k in _KEYS))
        QApplication.clipboard().setText('\n'.join(lines))
        QMessageBox.information(
            self, "Copiado",
            f"{len(self._filtered_data)} linha(s) copiadas para a área de transferência.")

    def _clear_log(self):
        reply = QMessageBox.question(
            self, "Limpar Log",
            "Deseja limpar todo o log de alterações desta sessão?\n\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_change_log()
            self._load_data()
