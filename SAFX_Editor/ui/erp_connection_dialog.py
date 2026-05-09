"""
Diálogo de configuração e uso de conexões ERP/DB externas
para importar dados SAFX diretamente sem precisar de arquivo TXT.
"""
import json
import logging
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QWidget, QGroupBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QCheckBox, QSpinBox, QMessageBox,
    QProgressBar, QFrame, QSplitter, QListWidget,
    QListWidgetItem, QSizePolicy, QApplication, QInputDialog,
)

from core.erp_connector import (
    ERPConnectionConfig, CONNECTOR_LABELS, CONNECTOR_PORTS,
    get_connector, check_dependencies, ERPConnectorError, OracleConnector,
)

logger = logging.getLogger(__name__)


class _FetchWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list, list, str)   # columns, rows, error

    def __init__(self, cfg, table_name, where_clause=''):
        super().__init__()
        self.cfg = cfg
        self.table_name = table_name
        self.where_clause = where_clause

    def run(self):
        try:
            connector = get_connector(self.cfg)
            cols, rows = connector.fetch_safx_table(
                self.table_name, self.where_clause,
                progress_cb=lambda n: self.progress.emit(n)
            )
            self.finished.emit(cols, rows, '')
        except Exception as e:
            self.finished.emit([], [], str(e))


class ERPConnectionDialog(QDialog):
    """
    Diálogo completo para:
    - Configurar conexões a Oracle, SAP, TOTVS, PostgreSQL, MySQL, Supabase, ODBC
    - Testar a conexão
    - Importar tabelas SAFX diretamente do ERP/banco
    """

    dataReady = pyqtSignal(str, list, list)   # table_name, columns, rows

    def __init__(self, db, layout_manager, parent=None, theme='dark'):
        super().__init__(parent)
        self.db = db
        self.layout_manager = layout_manager
        self.theme = theme
        self._worker: Optional[_FetchWorker] = None
        self._cfg = ERPConnectionConfig()

        self.setWindowTitle("Importar via ERP / Banco de Dados")
        self.setMinimumSize(860, 620)
        self.setModal(True)

        try:
            from ui.styles import get_style
            self.setStyleSheet(get_style(theme))
        except Exception:
            pass

        from ui.window_utils import enable_dialog_min_max
        enable_dialog_min_max(self)

        self._setup_ui()
        self._check_deps()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        hdr = QWidget()
        hdr.setFixedHeight(58)
        hdr.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0d2040,stop:1 #1a3060);"
            "border-bottom:2px solid #313244;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        t = QLabel("🔌  Importar Dados via ERP / Banco de Dados")
        t.setStyleSheet("color:#89b4fa;font-size:15px;font-weight:800;")
        hl.addWidget(t)
        hl.addStretch()
        self.lbl_dep_status = QLabel("")
        self.lbl_dep_status.setStyleSheet("font-size:11px;")
        hl.addWidget(self.lbl_dep_status)
        root.addWidget(hdr)

        from ui.window_utils import wrap_widget_in_scroll_area

        # ── Tabs: Conexão | Mapeamento | Importar ──
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root.addWidget(tabs, 1)

        tabs.addTab(wrap_widget_in_scroll_area(self._build_conn_tab(), tabs),
                    "  🔌 Conexão  ")
        tabs.addTab(wrap_widget_in_scroll_area(self._build_mapping_tab(), tabs),
                    "  🗺 Mapeamento  ")
        tabs.addTab(wrap_widget_in_scroll_area(self._build_import_tab(), tabs),
                    "  ⬇ Importar  ")

        self._main_tabs = tabs
        tabs.currentChanged.connect(self._on_erp_tab_changed)
        self._sync_import_combo_from_mapping()

        # ── Rodapé ──
        ftr = QWidget()
        ftr.setFixedHeight(50)
        ftr.setStyleSheet("border-top:1px solid #313244;")
        fl = QHBoxLayout(ftr)
        fl.setContentsMargins(16, 8, 16, 8)
        fl.setSpacing(8)

        self.lbl_status = QLabel("Configure a conexão e clique em Testar.")
        self.lbl_status.setStyleSheet("font-size:11px;")
        fl.addWidget(self.lbl_status)
        fl.addStretch()

        btn_close = QPushButton("Fechar")
        btn_close.setFixedHeight(32)
        btn_close.setFixedWidth(90)
        btn_close.clicked.connect(self.accept)
        fl.addWidget(btn_close)

        root.addWidget(ftr)

    def _gbox(self, title: str) -> QGroupBox:
        gb = QGroupBox(title)
        gb.setStyleSheet(
            "QGroupBox{color:#89b4fa;font-size:12px;font-weight:700;"
            "border:1px solid #1e3a5a;border-radius:6px;margin-top:8px;padding:10px;}"
            "QGroupBox::title{padding:0 6px;}")
        return gb

    def _lbl(self, txt: str) -> QLabel:
        l = QLabel(txt)
        l.setStyleSheet("color:#a6adc8;font-size:12px;")
        l.setFixedWidth(110)
        return l

    def _inp(self, placeholder='', pw=False) -> QLineEdit:
        e = QLineEdit()
        e.setFixedHeight(32)
        e.setPlaceholderText(placeholder)
        if pw:
            e.setEchoMode(QLineEdit.EchoMode.Password)
        e.setStyleSheet(
            "QLineEdit{background:#1a1a2e;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 10px;font-size:12px;}"
            "QLineEdit:focus{border-color:#89b4fa;}")
        return e

    # ── Aba Conexão ──

    def _build_conn_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # Tipo de conexão
        gb_type = self._gbox("Tipo de Sistema")
        tl = QHBoxLayout(gb_type)
        tl.addWidget(QLabel("Sistema:"))
        self.combo_type = QComboBox()
        for key, lbl in CONNECTOR_LABELS.items():
            self.combo_type.addItem(lbl, userData=key)
        self.combo_type.setFixedHeight(34)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        tl.addWidget(self.combo_type, 1)

        self.lbl_driver_status = QLabel("")
        self.lbl_driver_status.setStyleSheet("font-size:11px;")
        tl.addWidget(self.lbl_driver_status)
        lay.addWidget(gb_type)

        # Campos de conexão
        gb_conn = self._gbox("Parâmetros de Conexão")
        cl = QVBoxLayout(gb_conn)
        cl.setSpacing(6)

        def _row(label_txt, widget):
            row = QHBoxLayout()
            row.addWidget(self._lbl(label_txt))
            row.addWidget(widget, 1)
            cl.addLayout(row)

        self.edit_name = self._inp("Nome desta conexão (para identificação)")
        _row("Nome:", self.edit_name)

        self.edit_host = self._inp("ex: 192.168.1.100 ou erp.empresa.com")
        _row("Host / IP:", self.edit_host)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(0, 65535)
        self.spin_port.setFixedHeight(32)
        self.spin_port.setStyleSheet(
            "QSpinBox{background:#1a1a2e;color:#cdd6f4;border:1px solid #45475a;"
            "border-radius:5px;padding:2px 8px;font-size:12px;}")
        _row("Porta:", self.spin_port)

        self.edit_db = self._inp("Service name / Database / Company ID")
        _row("Database:", self.edit_db)

        self.edit_user = self._inp("Usuário")
        _row("Usuário:", self.edit_user)

        self.edit_pw = self._inp("Senha", pw=True)
        _row("Senha:", self.edit_pw)

        # SAP específico
        self.sap_frame = QWidget()
        sfl = QHBoxLayout(self.sap_frame)
        sfl.setContentsMargins(0, 0, 0, 0)
        sfl.setSpacing(10)
        sfl.addWidget(QLabel("Client:"))
        self.edit_sap_client = self._inp("100")
        self.edit_sap_client.setFixedWidth(80)
        sfl.addWidget(self.edit_sap_client)
        sfl.addWidget(QLabel("SysNr:"))
        self.edit_sap_sysnr = self._inp("00")
        self.edit_sap_sysnr.setFixedWidth(60)
        sfl.addWidget(self.edit_sap_sysnr)
        sfl.addWidget(QLabel("Lang:"))
        self.edit_sap_lang = self._inp("PT")
        self.edit_sap_lang.setFixedWidth(50)
        sfl.addWidget(self.edit_sap_lang)
        sfl.addStretch()
        self.sap_frame.setVisible(False)
        cl.addWidget(self.sap_frame)

        # REST / API URL
        row_api = QHBoxLayout()
        row_api.addWidget(self._lbl("API URL / DSN:"))
        self.edit_api_url = self._inp(
            "https://xxxx.supabase.co  ou  DSN=nome  ou  connection string")
        row_api.addWidget(self.edit_api_url, 1)
        cl.addLayout(row_api)

        row_key = QHBoxLayout()
        row_key.addWidget(self._lbl("API Key:"))
        self.edit_api_key = self._inp("Chave de API (Supabase / TOTVS JWT...)")
        row_key.addWidget(self.edit_api_key, 1)
        cl.addLayout(row_key)

        lay.addWidget(gb_conn)

        # Botão testar
        btn_test = QPushButton("🔌  Testar Conexão")
        btn_test.setFixedHeight(36)
        btn_test.setStyleSheet(
            "QPushButton{background:#1e3a5a;color:#89b4fa;border:none;"
            "border-radius:6px;font-size:13px;font-weight:700;}"
            "QPushButton:hover{background:#2a4a6a;color:white;}")
        btn_test.clicked.connect(self._test_connection)
        lay.addWidget(btn_test)

        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setWordWrap(True)
        self.lbl_test_result.setStyleSheet("font-size:12px;padding:4px;")
        lay.addWidget(self.lbl_test_result)

        lay.addStretch()
        self._on_type_changed(0)
        return w

    # ── Aba Mapeamento ──

    def _build_mapping_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        info = QLabel(
            "ℹ  Configure o nome da tabela no banco/ERP para cada tabela SAFX.\n"
            "Use «+ Adicionar tabela SAFX» para incluir códigos que não estão na lista.\n"
            "Deixe «Nome no Banco» em branco para usar o mesmo nome da SAFX.\n"
            "Você também pode escrever uma query SQL/endpoint personalizada.")
        info.setStyleSheet("color:#a6adc8;font-size:12px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        row_tool = QHBoxLayout()
        _btn_style = (
            "QPushButton{background:#1e3a5a;color:#89b4fa;border:1px solid #313244;"
            "border-radius:5px;padding:6px 12px;font-size:12px;font-weight:600;}"
            "QPushButton:hover{background:#2a4a6a;color:#cdd6f4;}")
        btn_add = QPushButton("+ Adicionar tabela SAFX…")
        btn_add.setToolTip(
            "Nova linha no mapeamento (ex.: SAFX07, SAFX_ORI_01, tabela Z do SAP).")
        btn_add.setStyleSheet(_btn_style)
        btn_add.clicked.connect(self._mapping_add_custom_row)
        row_tool.addWidget(btn_add)
        btn_rem = QPushButton("Remover linha selecionada")
        btn_rem.setToolTip("Remove a linha selecionada na grade.")
        btn_rem.setStyleSheet(_btn_style)
        btn_rem.clicked.connect(self._mapping_remove_selected_row)
        row_tool.addWidget(btn_rem)

        self._btn_list_oracle = QPushButton(
            "📋  Listar tabelas Oracle (schema do usuário)…")
        self._btn_list_oracle.setToolTip(
            "Usa host, porta, service name, usuário e senha da aba Conexão.\n"
            "Lista USER_TABLES (tabelas do próprio usuário). Para tabelas de "
            "outro owner (ex.: SAPSR3), use a coluna «Query personalizada» ou "
            "um usuário com acesso a esse schema.")
        self._btn_list_oracle.setStyleSheet(_btn_style)
        self._btn_list_oracle.clicked.connect(self._browse_oracle_tables_for_mapping)
        row_tool.addWidget(self._btn_list_oracle)
        row_tool.addStretch()
        lay.addLayout(row_tool)
        self._sync_oracle_list_button_visibility()

        self.tbl_mapping = QTableWidget(0, 3)
        self.tbl_mapping.setHorizontalHeaderLabels(
            ["Tabela SAFX", "Nome no Banco/ERP", "Query/Endpoint Personalizada"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed)
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.tbl_mapping.setColumnWidth(0, 120)
        self.tbl_mapping.setStyleSheet(
            "QTableWidget{background:#1a1a2e;color:#cdd6f4;"
            "gridline-color:#313244;border:1px solid #313244;}"
            "QHeaderView::section{background:#26263a;color:#89b4fa;"
            "font-weight:700;padding:5px;border:none;border-right:1px solid #313244;}")

        # Preenche com tabelas SAFX conhecidas
        known = [f'SAFX{n}' for n in [
            '01','04','05','07','08','14','21','24','25','30','31','34','35',
            '40','41','50','51','54','55','60','64','65','71','75','82','83',
            '92','93','96','97','108','109','118','119','128','139','148',
            '158','159','168','169','299','431','501','520','534','540',
            '702','992','993','2089','2098','2099']]
        self.tbl_mapping.setRowCount(len(known))
        for i, safx in enumerate(known):
            self.tbl_mapping.setItem(i, 0, self._mapping_editable_item(safx))
            self.tbl_mapping.setItem(i, 1, self._mapping_editable_item(''))
            self.tbl_mapping.setItem(i, 2, self._mapping_editable_item(''))
        self.tbl_mapping.itemChanged.connect(self._on_mapping_safx_cell_changed)

        lay.addWidget(self.tbl_mapping, 1)
        return w

    @staticmethod
    def _mapping_editable_item(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(
            it.flags()
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled)
        return it

    def _mapping_add_custom_row(self):
        text, ok = QInputDialog.getText(
            self, "Nova tabela SAFX",
            "Nome da tabela SAFX a mapear (ex.: SAFX07, SAFX_ORI_01):",
            QLineEdit.EchoMode.Normal,
            "")
        if not ok:
            return
        name = text.strip().upper().replace(' ', '_')
        if not name:
            return
        for i in range(self.tbl_mapping.rowCount()):
            c0 = self.tbl_mapping.item(i, 0)
            if c0 and c0.text().strip().upper() == name:
                QMessageBox.information(
                    self, "Duplicada",
                    f"A tabela «{name}» já existe na grade de mapeamento.")
                return
        r = self.tbl_mapping.rowCount()
        self.tbl_mapping.blockSignals(True)
        self.tbl_mapping.insertRow(r)
        self.tbl_mapping.setItem(r, 0, self._mapping_editable_item(name))
        self.tbl_mapping.setItem(r, 1, self._mapping_editable_item(''))
        self.tbl_mapping.setItem(r, 2, self._mapping_editable_item(''))
        self.tbl_mapping.blockSignals(False)
        self.tbl_mapping.selectRow(r)
        self._sync_import_combo_from_mapping()

    def _mapping_remove_selected_row(self):
        r = self.tbl_mapping.currentRow()
        if r < 0:
            QMessageBox.information(
                self, "Remover linha",
                "Selecione uma linha na grade de mapeamento para remover.")
            return
        self.tbl_mapping.removeRow(r)
        self._sync_import_combo_from_mapping()

    def _on_erp_tab_changed(self, index: int):
        if index == 2:
            self._sync_import_combo_from_mapping()

    def _sync_import_combo_from_mapping(self):
        if not hasattr(self, 'combo_import_table'):
            return
        names: List[str] = []
        seen = set()
        for i in range(self.tbl_mapping.rowCount()):
            it = self.tbl_mapping.item(i, 0)
            if not it:
                continue
            t = it.text().strip()
            if not t:
                continue
            key = t.upper()
            if key in seen:
                continue
            seen.add(key)
            names.append(t)
        names.sort(key=lambda x: x.upper())
        cur = self.combo_import_table.currentText().strip()
        self.combo_import_table.blockSignals(True)
        self.combo_import_table.clear()
        for n in names:
            self.combo_import_table.addItem(n)
        self.combo_import_table.blockSignals(False)
        if not names:
            self.combo_import_table.setEditText(cur)
            return
        pick = -1
        for i in range(self.combo_import_table.count()):
            if self.combo_import_table.itemText(i).upper() == cur.upper():
                pick = i
                break
        if pick >= 0:
            self.combo_import_table.setCurrentIndex(pick)
        else:
            self.combo_import_table.setEditText(cur if cur else names[0])

    def _on_mapping_safx_cell_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            self._sync_import_combo_from_mapping()

    def _sync_oracle_list_button_visibility(self):
        btn = getattr(self, '_btn_list_oracle', None)
        if btn is None:
            return
        key = self.combo_type.currentData()
        btn.setVisible(key == 'oracle')

    def _browse_oracle_tables_for_mapping(self):
        cfg = self._build_cfg()
        if cfg.type != 'oracle':
            QMessageBox.information(
                self, "Listagem",
                "A listagem automática de tabelas está disponível apenas para "
                "Oracle Database.")
            return
        if not check_dependencies().get('oracle'):
            QMessageBox.warning(
                self, "Driver Oracle ausente",
                "Instale um dos drivers no mesmo Python do SAFX Editor:\n\n"
                "  pip install oracledb\n\n"
                "(recomendado no Windows — modo «thin» costuma dispensar "
                "Oracle Instant Client)\n\n"
                "Alternativa:\n  pip install cx_Oracle\n\n"
                "Reinicie o aplicativo após instalar.")
            return
        if (not cfg.host.strip() or not (cfg.database or '').strip()
                or not cfg.username.strip()):
            QMessageBox.warning(
                self, "Dados incompletos",
                "Na aba Conexão, preencha host, database (service name) e usuário.")
            return

        row = self.tbl_mapping.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Linha do mapeamento",
                "Selecione uma linha na tabela de mapeamento; a coluna "
                "«Nome no Banco/ERP» será preenchida com o nome escolhido.")
            return

        try:
            conn = OracleConnector(cfg).connect()
        except Exception as e:
            QMessageBox.critical(self, "Conexão Oracle", str(e))
            return

        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT table_name FROM ("
                "  SELECT table_name FROM user_tables ORDER BY table_name"
                ") WHERE ROWNUM <= 8000"
            )
            names = [r[0] for r in cur.fetchall()]
        except Exception as e:
            QMessageBox.critical(self, "Consulta Oracle", str(e))
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not names:
            QMessageBox.information(
                self, "Nenhuma tabela",
                "Nenhuma entrada em USER_TABLES para este usuário.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Tabelas no schema Oracle (usuário atual)")
        dlg.setMinimumSize(440, 500)
        vl = QVBoxLayout(dlg)
        safx_cell = self.tbl_mapping.item(row, 0)
        safx_name = safx_cell.text() if safx_cell else "?"
        hint = QLabel(
            "Duplo clique em um nome ou clique em «Aplicar» para preencher "
            f"«Nome no Banco/ERP» na linha {safx_name}."
        )
        hint.setWordWrap(True)
        vl.addWidget(hint)
        fil = QLineEdit()
        fil.setPlaceholderText("Filtrar por nome…")
        vl.addWidget(fil)
        lst = QListWidget()
        for n in names:
            lst.addItem(n)
        lst.setAlternatingRowColors(True)
        vl.addWidget(lst, 1)

        def _filter_q():
            q = fil.text().strip().upper()
            for i in range(lst.count()):
                it = lst.item(i)
                it.setHidden(bool(q) and q not in it.text().upper())

        fil.textChanged.connect(lambda _t: _filter_q())

        def _apply_sel():
            items = lst.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "Seleção", "Selecione uma tabela na lista.")
                return
            name = items[0].text()
            c1 = self.tbl_mapping.item(row, 1)
            if not c1:
                c1 = self._mapping_editable_item('')
                self.tbl_mapping.setItem(row, 1, c1)
            c1.setText(name)
            dlg.accept()

        lst.itemDoubleClicked.connect(lambda _it: _apply_sel())

        bb = QHBoxLayout()
        b_apply = QPushButton("Aplicar à linha do mapeamento")
        b_apply.clicked.connect(_apply_sel)
        b_close = QPushButton("Fechar")
        b_close.clicked.connect(dlg.reject)
        bb.addWidget(b_apply)
        bb.addStretch()
        bb.addWidget(b_close)
        vl.addLayout(bb)

        dlg.exec()

    # ── Aba Importar ──

    def _build_import_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel("Tabela SAFX:"))
        self.combo_import_table = QComboBox()
        self.combo_import_table.setFixedHeight(34)
        # Adiciona tabelas conhecidas
        for n in ['SAFX01','SAFX04','SAFX05','SAFX07','SAFX08','SAFX14',
                  'SAFX21','SAFX24','SAFX25','SAFX30','SAFX31','SAFX34',
                  'SAFX35','SAFX40','SAFX41','SAFX50','SAFX51','SAFX60',
                  'SAFX82','SAFX83','SAFX92','SAFX93']:
            self.combo_import_table.addItem(n)
        self.combo_import_table.setEditable(True)
        top.addWidget(self.combo_import_table, 1)

        top.addWidget(QLabel("Filtro (WHERE):"))
        self.edit_where = self._inp("ex: COD_EMPRESA='001' AND ATIVO='S'")
        top.addWidget(self.edit_where, 2)
        lay.addLayout(top)

        btn_fetch = QPushButton("⬇  Buscar Dados do ERP")
        btn_fetch.setFixedHeight(36)
        btn_fetch.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #89b4fa,stop:1 #6495cd);"
            "color:#1e1e2e;border:none;border-radius:6px;"
            "font-size:13px;font-weight:800;}"
            "QPushButton:hover{background:#a0c4ff;}")
        btn_fetch.clicked.connect(self._fetch_data)
        lay.addWidget(btn_fetch)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar{background:#313244;border-radius:4px;border:none;}"
            "QProgressBar::chunk{background:#89b4fa;border-radius:4px;}")
        lay.addWidget(self.progress_bar)

        self.lbl_fetch_status = QLabel("")
        self.lbl_fetch_status.setStyleSheet("font-size:12px;")
        lay.addWidget(self.lbl_fetch_status)

        # Preview de dados
        self.preview_table = QTableWidget(0, 0)
        self.preview_table.setMinimumHeight(180)
        self.preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.preview_table.setStyleSheet(
            "QTableWidget{background:#1a1a2e;color:#cdd6f4;"
            "gridline-color:#313244;border:none;font-size:11px;font-family:Consolas;}"
            "QHeaderView::section{background:#26263a;color:#89b4fa;font-weight:700;"
            "padding:4px;border:none;border-right:1px solid #313244;}")
        lay.addWidget(self.preview_table, 1)

        btn_import = QPushButton("✔  Carregar no Sistema")
        btn_import.setFixedHeight(36)
        btn_import.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #40c878,stop:1 #2ea85a);"
            "color:#001a0a;border:none;border-radius:6px;"
            "font-size:13px;font-weight:800;}"
            "QPushButton:hover{background:#52e890;}"
            "QPushButton:disabled{background:#313244;color:#6c7086;}")
        btn_import.setEnabled(False)
        btn_import.clicked.connect(self._load_into_system)
        self._btn_import = btn_import
        self._fetched_cols: List[str] = []
        self._fetched_rows: List[Dict] = []
        lay.addWidget(btn_import)

        return w

    def _on_type_changed(self, idx: int):
        key = self.combo_type.currentData()
        port = CONNECTOR_PORTS.get(key, 0)
        self.spin_port.setValue(port)
        is_sap = key == 'sap_rfc'
        self.sap_frame.setVisible(is_sap)

        # Verifica disponibilidade do driver
        deps = check_dependencies()
        driver_key = 'supabase_rest' if key in ('supabase', 'supabase_rest') else key
        ok = deps.get(driver_key, True)
        if ok:
            self.lbl_driver_status.setText("✔ Driver disponível")
            self.lbl_driver_status.setStyleSheet("color:#a6e3a1;font-size:11px;")
        else:
            driver_pkgs = {
                'oracle': 'oracledb (recomendado) ou cx_Oracle',
                'postgres': 'psycopg2',
                'supabase_rest': 'requests', 'mysql': 'pymysql',
                'totvs_rest': 'requests', 'sap_rfc': 'pyrfc', 'odbc': 'pyodbc'
            }
            pkg = driver_pkgs.get(key, '?')
            self.lbl_driver_status.setText(f"⚠ pip install {pkg}")
            self.lbl_driver_status.setStyleSheet("color:#f9e2af;font-size:11px;")
        self._sync_oracle_list_button_visibility()

    def _build_cfg(self) -> ERPConnectionConfig:
        cfg = ERPConnectionConfig()
        cfg.type = self.combo_type.currentData() or 'postgres'
        cfg.display_name = self.edit_name.text().strip()
        cfg.host = self.edit_host.text().strip()
        cfg.port = self.spin_port.value()
        cfg.database = self.edit_db.text().strip()
        cfg.username = self.edit_user.text().strip()
        cfg.password = self.edit_pw.text()
        cfg.sap_client = self.edit_sap_client.text().strip() or '100'
        cfg.sap_sysnr = self.edit_sap_sysnr.text().strip() or '00'
        cfg.sap_lang = self.edit_sap_lang.text().strip() or 'PT'
        cfg.api_url = self.edit_api_url.text().strip()
        cfg.api_key = self.edit_api_key.text().strip()
        # Lê mapeamentos da tabela
        for i in range(self.tbl_mapping.rowCount()):
            safx = (self.tbl_mapping.item(i, 0) or QTableWidgetItem('')).text()
            mapped = (self.tbl_mapping.item(i, 1) or QTableWidgetItem('')).text()
            query = (self.tbl_mapping.item(i, 2) or QTableWidgetItem('')).text()
            if safx:
                if mapped:
                    cfg.table_mappings[safx] = mapped
                if query:
                    cfg.custom_queries[safx] = query
        return cfg

    def _test_connection(self):
        cfg = self._build_cfg()
        self.lbl_test_result.setText("Testando conexão…")
        QApplication.processEvents()
        try:
            connector = get_connector(cfg)
            conn = connector.connect()
            conn.close() if hasattr(conn, 'close') else None
            self.lbl_test_result.setText("✔  Conexão bem-sucedida!")
            self.lbl_test_result.setStyleSheet("color:#a6e3a1;font-size:12px;")
        except Exception as e:
            self.lbl_test_result.setText(f"✗  Erro: {e}")
            self.lbl_test_result.setStyleSheet("color:#f38ba8;font-size:12px;")

    def _check_deps(self):
        deps = check_dependencies()
        available = sum(1 for v in deps.values() if v)
        total = len(deps)
        self.lbl_dep_status.setText(
            f"{available}/{total} drivers disponíveis")
        color = "#a6e3a1" if available >= 2 else "#f9e2af"
        self.lbl_dep_status.setStyleSheet(f"color:{color};font-size:11px;")

    def _fetch_data(self):
        cfg = self._build_cfg()
        table_name = self.combo_import_table.currentText().strip()
        where = self.edit_where.text().strip()

        if not table_name:
            QMessageBox.warning(self, "Atenção", "Selecione ou digite o nome da tabela SAFX.")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.lbl_fetch_status.setText("Buscando dados…")
        self._btn_import.setEnabled(False)
        self.preview_table.clear()
        self.preview_table.setRowCount(0)

        self._worker = _FetchWorker(cfg, table_name, where)
        self._worker.progress.connect(self._on_fetch_progress)
        self._worker.finished.connect(self._on_fetch_finished)
        self._worker.start()

    def _on_fetch_progress(self, n: int):
        self.lbl_fetch_status.setText(f"Buscando… {n:,} linhas recebidas")

    def _on_fetch_finished(self, cols: List[str], rows: List[Dict], error: str):
        self.progress_bar.setVisible(False)

        if error:
            self.lbl_fetch_status.setText(f"✗ Erro: {error}")
            self.lbl_fetch_status.setStyleSheet("color:#f38ba8;")
            return

        self._fetched_cols = cols
        self._fetched_rows = rows

        self.lbl_fetch_status.setText(
            f"✔  {len(rows):,} registros recebidos  |  {len(cols)} campos")
        self.lbl_fetch_status.setStyleSheet("color:#a6e3a1;")

        # Preview (primeiras 50 linhas)
        self.preview_table.setColumnCount(len(cols))
        self.preview_table.setHorizontalHeaderLabels(cols)
        preview_rows = rows[:50]
        self.preview_table.setRowCount(len(preview_rows))
        for r, row in enumerate(preview_rows):
            for c, col in enumerate(cols):
                self.preview_table.setItem(r, c, QTableWidgetItem(row.get(col, '')))

        self._btn_import.setEnabled(bool(rows))

    def _load_into_system(self):
        if not self._fetched_rows:
            return
        table_name = self.combo_import_table.currentText().strip()

        # Converte para o formato da DB
        from core.database import ROW_ID_COL
        layout = self.layout_manager.get_layout(table_name)

        data = self._fetched_rows
        count = self.db.load_table(table_name, layout, data)
        self.dataReady.emit(table_name, self._fetched_cols, self._fetched_rows)
        QMessageBox.information(
            self, "Importação Concluída",
            f"✔  {count:,} registros de '{table_name}' carregados no sistema.\n\n"
            f"A tabela está disponível na aba Dados e no editor SQL.")
        self.accept()
