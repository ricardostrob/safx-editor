"""
Diálogo para importar planilhas externas (Excel / CSV) como tabelas auxiliares
para JOIN no editor SQL.
"""
import os
import csv
import threading
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QProgressBar, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QComboBox
)
from PyQt6.QtGui import QFont, QColor


class _ImportWorker(QThread):
    """Worker para leitura e importação em background."""
    progress = pyqtSignal(int, int)     # current, total
    finished = pyqtSignal(int, str)     # rows_imported, error_msg
    columns_ready = pyqtSignal(list)    # column names

    def __init__(self, db, file_path: str, table_name: str,
                 sheet_index: int = 0, skip_rows: int = 0,
                 has_header: bool = True, encoding: str = 'utf-8',
                 delimiter: str = ','):
        super().__init__()
        self.db = db
        self.file_path = file_path
        self.table_name = table_name
        self.sheet_index = sheet_index
        self.skip_rows = skip_rows
        self.has_header = has_header
        self.encoding = encoding
        self.delimiter = delimiter

    def run(self):
        try:
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext in ('.xlsx', '.xls', '.ods'):
                self._import_excel()
            else:
                self._import_csv()
        except Exception as e:
            self.finished.emit(0, str(e))

    def _import_excel(self):
        try:
            import openpyxl
        except ImportError:
            self.finished.emit(0, "openpyxl não encontrado. Execute: pip install openpyxl")
            return

        wb = openpyxl.load_workbook(self.file_path, read_only=True, data_only=True)
        sheet = wb.worksheets[min(self.sheet_index, len(wb.worksheets) - 1)]

        all_rows = list(sheet.iter_rows(values_only=True))

        # Pula linhas
        all_rows = all_rows[self.skip_rows:]

        if not all_rows:
            self.finished.emit(0, "Planilha vazia ou sem dados após as linhas ignoradas.")
            return

        if self.has_header:
            header = [str(c).strip() if c else f'COL_{i}' for i, c in enumerate(all_rows[0])]
            data_rows = all_rows[1:]
        else:
            header = [f'COL_{i}' for i in range(len(all_rows[0]))]
            data_rows = all_rows

        self.columns_ready.emit(header)
        total = len(data_rows)

        def _progress(n):
            self.progress.emit(n, total)

        count = self.db.import_external_table(
            self.table_name, header, data_rows, _progress)
        self.finished.emit(count, '')

    def _import_csv(self):
        with open(self.file_path, 'r', encoding=self.encoding, errors='replace') as f:
            lines = f.readlines()

        lines = lines[self.skip_rows:]
        if not lines:
            self.finished.emit(0, "Arquivo CSV vazio.")
            return

        reader_lines = csv.reader(lines, delimiter=self.delimiter)
        all_rows = list(reader_lines)

        if self.has_header and all_rows:
            header = [c.strip() if c.strip() else f'COL_{i}'
                      for i, c in enumerate(all_rows[0])]
            data_rows = all_rows[1:]
        else:
            header = [f'COL_{i}' for i in range(len(all_rows[0]) if all_rows else 0)]
            data_rows = all_rows

        self.columns_ready.emit(header)
        total = len(data_rows)

        def _progress(n):
            self.progress.emit(n, total)

        count = self.db.import_external_table(
            self.table_name, header, data_rows, _progress)
        self.finished.emit(count, '')


class ExternalImportDialog(QDialog):
    """
    Importa planilha externa (Excel .xlsx / CSV / TXT) como tabela temporária
    disponível para JOIN no editor SQL.
    """

    tableImported = pyqtSignal(str, list)   # table_name, columns

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Importar Planilha Externa para JOIN")
        self.setMinimumSize(780, 560)
        self.setModal(True)

        try:
            from ui.styles import MAIN_STYLE
            self.setStyleSheet(MAIN_STYLE)
        except Exception:
            pass

        self._file_path = ''
        self._columns: List[str] = []
        self._worker: Optional[_ImportWorker] = None

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #1a1a2e,stop:1 #0d1a2e);"
            "border-bottom:2px solid #313244;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel("📊  Importar Planilha Externa  —  JOIN com SAFX")
        lbl.setStyleSheet("color:#89b4fa;font-size:15px;font-weight:800;")
        h_lay.addWidget(lbl)
        root.addWidget(header)

        # ── Corpo ──
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 16, 20, 8)
        body_lay.setSpacing(12)

        # Seleção de arquivo
        file_group = QGroupBox("Arquivo")
        file_group.setStyleSheet(self._gstyle())
        fg = QVBoxLayout(file_group)
        fg.setSpacing(8)

        row_file = QHBoxLayout()
        self.edit_file = QLineEdit()
        self.edit_file.setReadOnly(True)
        self.edit_file.setPlaceholderText("Selecione um arquivo Excel (.xlsx), CSV ou TXT...")
        self.edit_file.setFixedHeight(34)
        self.edit_file.setStyleSheet(self._input_style())
        row_file.addWidget(self.edit_file)

        btn_browse = QPushButton("📂  Procurar...")
        btn_browse.setFixedHeight(34)
        btn_browse.setFixedWidth(130)
        btn_browse.clicked.connect(self._browse_file)
        row_file.addWidget(btn_browse)
        fg.addLayout(row_file)

        body_lay.addWidget(file_group)

        # Opções de importação
        opt_group = QGroupBox("Opções de Importação")
        opt_group.setStyleSheet(self._gstyle())
        og = QHBoxLayout(opt_group)
        og.setSpacing(16)

        # Nome da tabela
        col_name = QVBoxLayout()
        col_name.addWidget(QLabel("Nome da Tabela (para SQL):"))
        self.edit_tname = QLineEdit()
        self.edit_tname.setFixedHeight(32)
        self.edit_tname.setPlaceholderText("ex: ext_ajustes")
        self.edit_tname.setStyleSheet(self._input_style())
        col_name.addWidget(self.edit_tname)
        og.addLayout(col_name)

        # Aba/Planilha (Excel)
        col_sheet = QVBoxLayout()
        col_sheet.addWidget(QLabel("Aba (Excel, base 0):"))
        self.spin_sheet = QSpinBox()
        self.spin_sheet.setMinimum(0)
        self.spin_sheet.setMaximum(50)
        self.spin_sheet.setFixedHeight(32)
        self.spin_sheet.setStyleSheet(
            "QSpinBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 6px;font-size:12px;}")
        col_sheet.addWidget(self.spin_sheet)
        og.addLayout(col_sheet)

        # Linhas a ignorar
        col_skip = QVBoxLayout()
        col_skip.addWidget(QLabel("Ignorar N linhas iniciais:"))
        self.spin_skip = QSpinBox()
        self.spin_skip.setMinimum(0)
        self.spin_skip.setMaximum(100)
        self.spin_skip.setFixedHeight(32)
        self.spin_skip.setStyleSheet(
            "QSpinBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 6px;font-size:12px;}")
        col_skip.addWidget(self.spin_skip)
        og.addLayout(col_skip)

        # Tem cabeçalho?
        col_hdr = QVBoxLayout()
        col_hdr.addWidget(QLabel(" "))
        self.chk_header = QCheckBox("1ª linha é cabeçalho")
        self.chk_header.setChecked(True)
        self.chk_header.setStyleSheet("color:#cdd6f4;font-size:12px;")
        col_hdr.addWidget(self.chk_header)
        og.addLayout(col_hdr)

        # Delimitador (CSV)
        col_delim = QVBoxLayout()
        col_delim.addWidget(QLabel("Delimitador (CSV):"))
        self.combo_delim = QComboBox()
        self.combo_delim.addItems([
            "Vírgula (,)",
            "Ponto e vírgula (;)",
            "Tabulação (\\t)",
            "Pipe (|)",
            "Espaço ( )",
        ])
        self.combo_delim.setFixedHeight(32)
        self.combo_delim.setStyleSheet(
            "QComboBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 8px;font-size:12px;}")
        col_delim.addWidget(self.combo_delim)
        og.addLayout(col_delim)

        # Encoding
        col_enc = QVBoxLayout()
        col_enc.addWidget(QLabel("Encoding:"))
        self.combo_enc = QComboBox()
        self.combo_enc.addItems(['utf-8', 'latin-1', 'cp1252', 'utf-16'])
        self.combo_enc.setFixedHeight(32)
        self.combo_enc.setStyleSheet(
            "QComboBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 8px;font-size:12px;}")
        col_enc.addWidget(self.combo_enc)
        og.addLayout(col_enc)

        body_lay.addWidget(opt_group)

        # Preview de colunas detectadas
        prev_group = QGroupBox("Colunas Detectadas (preview)")
        prev_group.setStyleSheet(self._gstyle())
        pg = QVBoxLayout(prev_group)

        self.tbl_preview = QTableWidget(0, 0)
        self.tbl_preview.setMinimumHeight(100)
        self.tbl_preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.tbl_preview.setStyleSheet(
            "QTableWidget{background:#1e1e2e;color:#cdd6f4;gridline-color:#313244;"
            "border:none;font-family:Consolas;font-size:11px;}"
            "QHeaderView::section{background:#313244;color:#89b4fa;font-weight:700;"
            "padding:4px;border:none;border-right:1px solid #45475a;}")
        pg.addWidget(self.tbl_preview)

        self.lbl_preview_info = QLabel("")
        self.lbl_preview_info.setStyleSheet("color:#a6adc8;font-size:11px;margin-top:4px;")
        pg.addWidget(self.lbl_preview_info)

        body_lay.addWidget(prev_group, 1)

        # Sugestão SQL
        sql_group = QGroupBox("Exemplo de JOIN gerado automaticamente")
        sql_group.setStyleSheet(self._gstyle())
        sg = QVBoxLayout(sql_group)
        self.lbl_sql_hint = QLabel(
            "Selecione um arquivo e importe para ver um exemplo de JOIN...")
        self.lbl_sql_hint.setStyleSheet(
            "color:#a6e3a1;font-family:Consolas;font-size:11px;"
            "background:#0d1a0d;padding:8px 12px;border-radius:5px;"
            "border:1px solid #1a4e1a;")
        self.lbl_sql_hint.setWordWrap(True)
        sg.addWidget(self.lbl_sql_hint)
        body_lay.addWidget(sql_group)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar{background:#313244;border-radius:4px;border:none;}"
            "QProgressBar::chunk{background:#89b4fa;border-radius:4px;}")
        body_lay.addWidget(self.progress)

        root.addWidget(body, 1)

        # ── Botões ──
        btn_bar = QWidget()
        btn_bar.setFixedHeight(52)
        btn_bar.setStyleSheet("background:#181825;border-top:1px solid #313244;")
        b_lay = QHBoxLayout(btn_bar)
        b_lay.setContentsMargins(16, 8, 16, 8)
        b_lay.setSpacing(8)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#a6adc8;font-size:11px;")
        b_lay.addWidget(self.lbl_status)
        b_lay.addStretch()

        btn_cancel = QPushButton("Fechar")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setFixedWidth(90)
        btn_cancel.clicked.connect(self.accept)
        b_lay.addWidget(btn_cancel)

        self.btn_import = QPushButton("📊  Importar Planilha")
        self.btn_import.setFixedHeight(34)
        self.btn_import.setMinimumWidth(160)
        self.btn_import.setEnabled(False)
        self.btn_import.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "  stop:0 #89b4fa,stop:1 #6495cd);"
            "color:#1e1e2e;border:none;border-radius:6px;"
            "font-size:13px;font-weight:800;padding:0 16px;}"
            "QPushButton:hover{background:#a0c4ff;}"
            "QPushButton:disabled{background:#313244;color:#6c7086;}")
        self.btn_import.clicked.connect(self._start_import)
        b_lay.addWidget(self.btn_import)

        root.addWidget(btn_bar)

    def _gstyle(self) -> str:
        return ("QGroupBox{color:#a6adc8;font-size:12px;font-weight:700;"
                "border:1px solid #313244;border-radius:6px;"
                "margin-top:8px;padding:10px;}"
                "QGroupBox::title{padding:0 6px;}")

    def _input_style(self) -> str:
        return ("QLineEdit{font-size:12px;background:#26263a;color:#cdd6f4;"
                "border:1px solid #45475a;border-radius:5px;padding:2px 10px;}"
                "QLineEdit:focus{border-color:#89b4fa;}")

    def _get_delimiter(self) -> str:
        idx = self.combo_delim.currentIndex()
        return [',', ';', '\t', '|', ' '][idx]

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Planilha ou CSV",
            os.path.expanduser('~'),
            "Planilhas (*.xlsx *.xls *.csv *.txt *.tsv *.ods);;"
            "Excel (*.xlsx *.xls);;"
            "CSV / TXT (*.csv *.txt *.tsv);;"
            "Todos (*.*)"
        )
        if not path:
            return
        self._file_path = path
        self.edit_file.setText(path)

        # Sugere nome para a tabela com base no arquivo
        base = os.path.splitext(os.path.basename(path))[0]
        safe = ''.join(c if c.isalnum() else '_' for c in base)[:30]
        if not self.edit_tname.text():
            self.edit_tname.setText(f'ext_{safe}')

        # Detecta delimiter para CSV
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.tsv',):
            self.combo_delim.setCurrentIndex(2)
        elif ext in ('.csv',):
            self.combo_delim.setCurrentIndex(0)

        self.btn_import.setEnabled(True)
        self.lbl_status.setText("Arquivo selecionado. Configure as opções e clique em Importar.")

    def _start_import(self):
        table_name = self.edit_tname.text().strip()
        if not table_name:
            QMessageBox.warning(self, "Atenção", "Informe um nome para a tabela.")
            return
        if not table_name[0].isalpha() and table_name[0] != '_':
            QMessageBox.warning(self, "Atenção",
                                "O nome da tabela deve começar com letra ou underscore.")
            return

        self.btn_import.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.lbl_status.setText("Importando...")
        self.tbl_preview.clear()
        self.tbl_preview.setRowCount(0)
        self.tbl_preview.setColumnCount(0)

        self._worker = _ImportWorker(
            db=self.db,
            file_path=self._file_path,
            table_name=table_name,
            sheet_index=self.spin_sheet.value(),
            skip_rows=self.spin_skip.value(),
            has_header=self.chk_header.isChecked(),
            encoding=self.combo_enc.currentText(),
            delimiter=self._get_delimiter(),
        )
        self._worker.columns_ready.connect(self._on_columns_ready)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_columns_ready(self, columns: List[str]):
        self._columns = columns
        self.tbl_preview.setColumnCount(len(columns))
        self.tbl_preview.setHorizontalHeaderLabels(columns)
        self.tbl_preview.setRowCount(0)

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        self.lbl_status.setText(f"Importando... {current:,} linhas processadas")

    def _on_finished(self, count: int, error: str):
        self.progress.setVisible(False)
        self.btn_import.setEnabled(True)

        if error:
            self.lbl_status.setText(f"❌ Erro: {error}")
            QMessageBox.critical(self, "Erro na Importação", error)
            return

        table_name = self.edit_tname.text().strip()
        self.lbl_status.setText(
            f"✔  {count:,} linhas importadas na tabela '{table_name}'")
        self.lbl_preview_info.setText(
            f"{len(self._columns)} coluna(s) detectadas  •  {count:,} linha(s) importadas")

        # Gera sugestão de JOIN
        loaded = list(self.db.loaded_tables.keys())
        safx_ex = loaded[0] if loaded else 'SAFX07'
        col1 = self._columns[0] if self._columns else 'COL_0'
        hint = (
            f"-- Tabela '{table_name}' pronta para uso no SQL!\n\n"
            f"SELECT s.*, e.{col1}\n"
            f"FROM {safx_ex} s\n"
            f"JOIN {table_name} e\n"
            f"  ON s.COD_ESTAB = e.{col1}\n"
            f"LIMIT 100;"
        )
        self.lbl_sql_hint.setText(hint)

        self.tableImported.emit(table_name, self._columns)
