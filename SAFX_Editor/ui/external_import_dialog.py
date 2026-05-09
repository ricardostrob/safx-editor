"""
Diálogo para importar planilhas externas (Excel / CSV) como tabelas auxiliares
para JOIN no editor SQL.
"""
import os
import csv
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEventLoop
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QProgressBar, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QComboBox, QApplication,
)
from PyQt6.QtGui import QFont, QColor


class _ImportWorker(QThread):
    """
    Só lê o arquivo em thread secundária.
    A gravação no SQLite ocorre na thread da UI (evita crash do sqlite/Qt).
    """
    progress = pyqtSignal(int, int)     # current, total (durante leitura)
    read_finished = pyqtSignal(str)     # '' = sucesso; senão mensagem de erro
    columns_ready = pyqtSignal(list)      # nomes das colunas (cabeçalho)

    def __init__(self, file_path: str, table_name: str,
                 sheet_index: int = 0, skip_rows: int = 0,
                 has_header: bool = True, encoding: str = 'utf-8',
                 delimiter: str = ','):
        super().__init__()
        self.file_path = file_path
        self.table_name = table_name
        self.sheet_index = sheet_index
        self.skip_rows = skip_rows
        self.has_header = has_header
        self.encoding = encoding
        self.delimiter = delimiter
        self.parse_header: List[str] = []
        self.parse_rows: List[List] = []

    def run(self):
        err = ''
        self.parse_header = []
        self.parse_rows = []
        try:
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext in ('.xlsx', '.xls', '.ods'):
                err = self._read_excel()
            else:
                err = self._read_csv()
        except Exception as e:
            err = str(e)
        self.read_finished.emit(err)

    def _read_excel(self) -> str:
        try:
            import openpyxl
        except ImportError:
            return "openpyxl não encontrado. Execute: pip install openpyxl"

        wb = None
        try:
            wb = openpyxl.load_workbook(
                self.file_path, read_only=True, data_only=True)
            sheet = wb.worksheets[min(self.sheet_index, len(wb.worksheets) - 1)]

            all_rows = list(sheet.iter_rows(values_only=True))
            all_rows = all_rows[self.skip_rows:]

            if not all_rows:
                return ("Planilha vazia ou sem dados após as linhas ignoradas.")

            if self.has_header:
                header = [
                    str(c).strip() if c else f'COL_{i}'
                    for i, c in enumerate(all_rows[0])]
                data_rows = all_rows[1:]
            else:
                header = [f'COL_{i}' for i in range(len(all_rows[0]))]
                data_rows = all_rows

            self.columns_ready.emit(header)
            total = len(data_rows)
            self.progress.emit(0, max(1, total))

            self.parse_header = list(header)
            self.parse_rows = [list(r) for r in data_rows]
            return ''
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    def _read_csv(self) -> str:
        with open(self.file_path, 'r', encoding=self.encoding, errors='replace') as f:
            lines = f.readlines()

        lines = lines[self.skip_rows:]
        if not lines:
            return "Arquivo CSV vazio."

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
        self.progress.emit(0, max(1, total))

        self.parse_header = list(header)
        self.parse_rows = [list(r) for r in data_rows]
        return ''


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
        self.setMinimumSize(720, 420)
        self.setModal(True)

        try:
            from ui.styles import MAIN_STYLE
            self.setStyleSheet(MAIN_STYLE)
        except Exception:
            pass

        from ui.window_utils import enable_dialog_min_max
        enable_dialog_min_max(self)

        self._file_path = ''
        self._columns: List[str] = []
        self._worker: Optional[_ImportWorker] = None
        self._writing_db = False

        self._setup_ui()

    def _setup_ui(self):
        from ui.window_utils import wrap_widget_in_scroll_area

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
        og = QGridLayout(opt_group)
        og.setHorizontalSpacing(14)
        og.setVerticalSpacing(10)
        og.setColumnStretch(1, 1)
        og.setColumnStretch(3, 1)

        og.addWidget(QLabel("Nome da tabela (SQL):"), 0, 0)
        self.edit_tname = QLineEdit()
        self.edit_tname.setMinimumHeight(32)
        self.edit_tname.setPlaceholderText("ex: ext_ajustes")
        self.edit_tname.setStyleSheet(self._input_style())
        og.addWidget(self.edit_tname, 0, 1, 1, 3)

        og.addWidget(QLabel("Aba Excel (base 0):"), 1, 0)
        self.spin_sheet = QSpinBox()
        self.spin_sheet.setMinimum(0)
        self.spin_sheet.setMaximum(50)
        self.spin_sheet.setMinimumHeight(32)
        self.spin_sheet.setStyleSheet(
            "QSpinBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 6px;font-size:12px;}")
        og.addWidget(self.spin_sheet, 1, 1)

        og.addWidget(QLabel("Ignorar linhas no início:"), 1, 2)
        self.spin_skip = QSpinBox()
        self.spin_skip.setMinimum(0)
        self.spin_skip.setMaximum(100)
        self.spin_skip.setMinimumHeight(32)
        self.spin_skip.setStyleSheet(
            "QSpinBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 6px;font-size:12px;}")
        og.addWidget(self.spin_skip, 1, 3)

        self.chk_header = QCheckBox("1ª linha é cabeçalho")
        self.chk_header.setChecked(True)
        self.chk_header.setStyleSheet("color:#cdd6f4;font-size:12px;")
        og.addWidget(self.chk_header, 2, 0, 1, 2)

        og.addWidget(QLabel("Delimitador (CSV):"), 2, 2)
        self.combo_delim = QComboBox()
        self.combo_delim.addItems([
            "Vírgula (,)",
            "Ponto e vírgula (;)",
            "Tabulação (\\t)",
            "Pipe (|)",
            "Espaço ( )",
        ])
        self.combo_delim.setMinimumHeight(32)
        self.combo_delim.setStyleSheet(
            "QComboBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 8px;font-size:12px;}")
        og.addWidget(self.combo_delim, 2, 3)

        og.addWidget(QLabel("Encoding:"), 3, 0)
        self.combo_enc = QComboBox()
        self.combo_enc.addItems(['utf-8', 'latin-1', 'cp1252', 'utf-16'])
        self.combo_enc.setMinimumHeight(32)
        self.combo_enc.setStyleSheet(
            "QComboBox{background:#26263a;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 8px;font-size:12px;}")
        og.addWidget(self.combo_enc, 3, 1)

        self.spin_skip.valueChanged.connect(lambda _v: self._refresh_csv_preview())
        self.spin_sheet.valueChanged.connect(lambda _v: self._refresh_csv_preview())
        self.chk_header.toggled.connect(self._refresh_csv_preview)
        self.combo_delim.currentIndexChanged.connect(self._refresh_csv_preview)
        self.combo_enc.currentIndexChanged.connect(self._refresh_csv_preview)

        body_lay.addWidget(opt_group)

        # Preview de colunas detectadas
        prev_group = QGroupBox("Colunas Detectadas (preview)")
        prev_group.setStyleSheet(self._gstyle())
        pg = QVBoxLayout(prev_group)

        self.tbl_preview = QTableWidget(0, 0)
        self.tbl_preview.setMinimumHeight(72)
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

        scroll = wrap_widget_in_scroll_area(body, self)
        root.addWidget(scroll, 1)

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
        btn_cancel.clicked.connect(self.reject)
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

    @staticmethod
    def _sniff_delimiter_from_line(line: str) -> str:
        """Escolhe o delimitador mais provável na primeira linha de dados."""
        if not line.strip():
            return ','
        tabs = line.count('\t')
        semis = line.count(';')
        commas = line.count(',')
        if tabs >= 1 and tabs >= max(semis, commas):
            return '\t'
        if semis > commas:
            return ';'
        return ','

    def _set_delimiter_combo(self, delim: str):
        order = [',', ';', '\t', '|', ' ']
        if delim in order:
            self.combo_delim.setCurrentIndex(order.index(delim))

    def _refresh_csv_preview(self):
        """Atualiza a grade de pré-visualização (CSV/TXT) com o delimitador atual."""
        path = self._file_path
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in ('.csv', '.txt', '.tsv'):
            self.tbl_preview.setRowCount(0)
            self.tbl_preview.setColumnCount(0)
            self.lbl_preview_info.setText(
                "Para Excel (.xlsx), as colunas aparecem após importar.")
            return
        enc = self.combo_enc.currentText()
        try:
            with open(path, 'r', encoding=enc, errors='replace') as f:
                raw_lines = f.readlines()
        except OSError as e:
            self.lbl_preview_info.setText(f"Não foi possível ler o arquivo: {e}")
            return
        skip = self.spin_skip.value()
        lines = raw_lines[skip:]
        while lines and lines[0].strip() == '':
            lines.pop(0)
        if not lines:
            self.lbl_preview_info.setText("Nenhuma linha após ignorar início.")
            return
        delim = self._get_delimiter()
        reader = csv.reader([lines[0].rstrip('\n').rstrip('\r')], delimiter=delim)
        try:
            first = next(reader)
        except StopIteration:
            first = []
        ncols = len(first)
        if ncols <= 1 and delim == ',' and ';' in lines[0]:
            delim = ';'
            self.combo_delim.blockSignals(True)
            self._set_delimiter_combo(';')
            self.combo_delim.blockSignals(False)
            reader = csv.reader([lines[0].rstrip('\n').rstrip('\r')], delimiter=delim)
            first = next(reader)
            ncols = len(first)

        if self.chk_header.isChecked():
            headers = [c.strip() or f'COL_{i}' for i, c in enumerate(first)]
            data_start = 1
        else:
            headers = [f'COL_{i}' for i in range(ncols)]
            data_start = 0

        self.tbl_preview.clear()
        self.tbl_preview.setColumnCount(len(headers))
        self.tbl_preview.setHorizontalHeaderLabels(headers)
        max_rows = min(8, len(lines) - data_start)
        self.tbl_preview.setRowCount(max_rows)
        for ri in range(max_rows):
            line = lines[data_start + ri]
            parsed = list(csv.reader(
                [line.rstrip('\n').rstrip('\r')], delimiter=delim))
            row_vals = parsed[0] if parsed else []
            for ci, h in enumerate(headers):
                val = row_vals[ci] if ci < len(row_vals) else ''
                self.tbl_preview.setItem(ri, ci, QTableWidgetItem(val))
        total_data = max(0, len(lines) - data_start)
        if self.chk_header.isChecked():
            total_data = max(0, total_data - 1)
        self.lbl_preview_info.setText(
            f"{len(headers)} coluna(s) detectadas  •  ~{total_data:,} linha(s) de dados (estimativa)")

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

        ext = os.path.splitext(path)[1].lower()
        if ext in ('.tsv',):
            self.combo_delim.blockSignals(True)
            self._set_delimiter_combo('\t')
            self.combo_delim.blockSignals(False)
        elif ext in ('.csv', '.txt'):
            try:
                enc = self.combo_enc.currentText()
                with open(path, 'r', encoding=enc, errors='replace') as f:
                    chunk = []
                    for _ in range(self.spin_skip.value() + 3):
                        ln = f.readline()
                        if not ln:
                            break
                        chunk.append(ln)
                body = ''.join(chunk[self.spin_skip.value():])
                first = ''
                for line in body.splitlines():
                    if line.strip():
                        first = line
                        break
                if first:
                    self.combo_delim.blockSignals(True)
                    self._set_delimiter_combo(self._sniff_delimiter_from_line(first))
                    self.combo_delim.blockSignals(False)
            except OSError:
                pass

        self.btn_import.setEnabled(True)
        self.lbl_status.setText("Arquivo selecionado. Revise delimitador e pré-visualização.")
        self._refresh_csv_preview()

    def _start_import(self):
        table_name = self.edit_tname.text().strip()
        if not table_name:
            QMessageBox.warning(self, "Atenção", "Informe um nome para a tabela.")
            return
        if not table_name[0].isalpha() and table_name[0] != '_':
            QMessageBox.warning(self, "Atenção",
                                "O nome da tabela deve começar com letra ou underscore.")
            return
        if not self._file_path or not os.path.isfile(self._file_path):
            QMessageBox.warning(
                self, "Atenção",
                "Selecione um arquivo válido com «Procurar…» antes de importar.")
            return
        if self._writing_db:
            QMessageBox.information(
                self, "Aguarde",
                "A gravação no banco de dados ainda não terminou.")
            return
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                self, "Aguarde", "Uma importação já está em andamento.")
            return

        self.btn_import.setEnabled(False)
        self._writing_db = True
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.lbl_status.setText("Lendo arquivo…")
        self.tbl_preview.clear()
        self.tbl_preview.setRowCount(0)
        self.tbl_preview.setColumnCount(0)

        self._worker = _ImportWorker(
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
        self._worker.read_finished.connect(self._on_read_finished)
        self._worker.start()

    def _on_read_finished(self, err: str):
        """Leitura do arquivo terminou (thread). Gravação SQLite na thread da UI."""
        w = self._worker
        if w is None:
            self._writing_db = False
            self.btn_import.setEnabled(True)
            self.progress.setVisible(False)
            return

        if err:
            self.progress.setVisible(False)
            self.btn_import.setEnabled(True)
            self._writing_db = False
            self.lbl_status.setText(f"❌ Erro: {err}")
            QMessageBox.critical(self, "Erro na leitura", err)
            w.deleteLater()
            self._worker = None
            return

        self.lbl_status.setText("Gravando no banco de dados…")
        n = len(w.parse_rows)
        self.progress.setRange(0, max(1, n))
        self.progress.setValue(0)
        self.progress.setVisible(True)

        def db_prog(processed: int):
            self.progress.setValue(min(processed, n))
            QApplication.processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

        try:
            count, sql_table = self.db.import_external_table(
                w.table_name, w.parse_header, w.parse_rows, db_prog)
        except Exception as e:
            self.progress.setVisible(False)
            self.btn_import.setEnabled(True)
            self._writing_db = False
            self.lbl_status.setText(f"❌ Erro ao gravar: {e}")
            QMessageBox.critical(
                self, "Erro ao gravar no SQLite",
                str(e))
            w.deleteLater()
            self._worker = None
            return

        w.deleteLater()
        self._worker = None
        self._apply_import_success(count, sql_table)

    def _apply_import_success(self, count: int, sql_table: str):
        """Atualiza UI após gravar no SQLite (thread principal)."""
        self.progress.setVisible(False)
        self.btn_import.setEnabled(True)
        self._writing_db = False

        t_sql = (sql_table or self.edit_tname.text().strip()).strip()
        if t_sql and t_sql != self.edit_tname.text().strip():
            self.edit_tname.setText(t_sql)

        self.lbl_status.setText(
            f"✔  {count:,} linhas importadas na tabela «{t_sql}»")

        try:
            sql_cols = self.db.get_table_columns(t_sql)
        except Exception:
            sql_cols = list(self._columns)

        self.lbl_preview_info.setText(
            f"{len(sql_cols)} coluna(s) na tabela  •  {count:,} linha(s) importadas")

        loaded = list(self.db.loaded_tables.keys())
        safx_ex = loaded[0] if loaded else 'SAFX07'
        hint = self.db.build_external_join_example_sql(
            safx_ex, t_sql, sql_cols).strip()
        self.lbl_sql_hint.setText(hint)

        try:
            self.tableImported.emit(t_sql, sql_cols)
            self.accept()
        except Exception as ex:
            QMessageBox.critical(
                self, "Erro",
                f"Importação concluída, mas falhou ao atualizar a janela principal:\n{ex}")

    def _on_columns_ready(self, columns: List[str]):
        self._columns = columns
        self.tbl_preview.setColumnCount(len(columns))
        self.tbl_preview.setHorizontalHeaderLabels(columns)
        self.tbl_preview.setRowCount(0)

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        self.lbl_status.setText(f"Lendo arquivo… {current:,} / {total:,} linhas")
