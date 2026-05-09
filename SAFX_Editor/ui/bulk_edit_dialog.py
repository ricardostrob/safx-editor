"""
Diálogo de edição em lote — define o mesmo valor para N linhas de uma só vez.
"""
from typing import List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QWidget, QFrame, QTextEdit,
    QMessageBox, QCheckBox, QGroupBox
)


class BulkEditDialog(QDialog):
    """
    Permite editar o valor de UMA coluna em MÚLTIPLAS linhas de uma só vez.
    Também suporta incremento, substituição parcial e limpeza de campo.
    """

    def __init__(self, field_name: str, row_count: int,
                 current_sample: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self.field_name = field_name
        self.row_count = row_count
        self.current_sample = current_sample or ''
        self._result_value: Optional[str] = None
        self._mode: str = 'set'   # 'set' | 'clear' | 'replace' | 'prefix' | 'suffix'

        self.setWindowTitle(f"Edição em Lote — {field_name}")
        self.setMinimumWidth(520)
        self.setModal(True)

        from ui.styles import MAIN_STYLE
        self.setStyleSheet(MAIN_STYLE)
        from ui.window_utils import enable_dialog_min_max, wrap_widget_in_scroll_area
        enable_dialog_min_max(self)
        self._setup_ui()

    def _setup_ui(self):
        from ui.window_utils import wrap_widget_in_scroll_area

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #1a1a2e, stop:1 #2a1a3e);"
            "border-bottom: 2px solid #313244;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 0, 20, 0)

        lbl = QLabel(f"✎  Edição em Lote  —  Campo: {self.field_name}")
        lbl.setStyleSheet(
            "color:#cba6f7; font-size:15px; font-weight:800;")
        h_lay.addWidget(lbl)

        h_lay.addStretch()

        count_lbl = QLabel(f"{self.row_count:,} linha(s) selecionada(s)")
        count_lbl.setStyleSheet("color:#89b4fa; font-size:12px; font-weight:700;")
        h_lay.addWidget(count_lbl)

        layout.addWidget(header)

        # ── Corpo ──
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 16, 20, 16)
        body_lay.setSpacing(12)

        # Amostra do valor atual
        if self.current_sample:
            sample_lbl = QLabel(
                f"Valor atual (primeira linha selecionada): "
                f"<b style='color:#89b4fa;'>{self.current_sample[:60]}</b>")
            sample_lbl.setStyleSheet("color:#a6adc8; font-size:12px;")
            sample_lbl.setWordWrap(True)
            body_lay.addWidget(sample_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#313244;")
        body_lay.addWidget(sep)

        # Modo de edição
        mode_group = QGroupBox("Modo de Edição")
        mode_group.setStyleSheet(
            "QGroupBox{color:#a6adc8;font-size:12px;font-weight:700;"
            "border:1px solid #313244;border-radius:6px;margin-top:8px;padding:8px;}"
            "QGroupBox::title{padding:0 6px;}")
        mode_lay = QVBoxLayout(mode_group)
        mode_lay.setSpacing(6)

        self.rb_set = self._make_rb(
            "🖊  Definir valor fixo",
            "Todas as linhas receberão exatamente o valor digitado", True)
        self.rb_clear = self._make_rb(
            "🗑  Limpar campo (valor vazio)",
            "Todas as linhas terão o campo zerado/vazio")
        self.rb_replace = self._make_rb(
            "🔄  Substituir parte do texto",
            "Substitui uma substring em todas as linhas (localizar → substituir)")
        self.rb_prefix = self._make_rb(
            "⬅  Adicionar prefixo",
            "Insere texto no início do valor atual de cada linha")
        self.rb_suffix = self._make_rb(
            "➡  Adicionar sufixo",
            "Adiciona texto no final do valor atual de cada linha")

        for rb in (self.rb_set, self.rb_clear, self.rb_replace,
                   self.rb_prefix, self.rb_suffix):
            mode_lay.addWidget(rb)
            rb.clicked.connect(self._update_inputs)

        body_lay.addWidget(mode_group)

        # Inputs dinâmicos
        self.input_group = QGroupBox("Valor")
        self.input_group.setStyleSheet(
            "QGroupBox{color:#a6adc8;font-size:12px;font-weight:700;"
            "border:1px solid #313244;border-radius:6px;margin-top:8px;padding:8px;}"
            "QGroupBox::title{padding:0 6px;}")
        input_lay = QVBoxLayout(self.input_group)
        input_lay.setSpacing(6)

        # Linha 1: valor principal / localizar
        row1 = QHBoxLayout()
        self.lbl_val = QLabel("Novo valor:")
        self.lbl_val.setFixedWidth(100)
        self.lbl_val.setStyleSheet("color:#a6adc8; font-size:12px;")
        row1.addWidget(self.lbl_val)

        self.edit_value = QLineEdit()
        self.edit_value.setFixedHeight(34)
        self.edit_value.setStyleSheet(
            "QLineEdit{font-size:13px;background:#26263a;color:#cdd6f4;"
            "border:1px solid #45475a;border-radius:5px;padding:2px 10px;}"
            "QLineEdit:focus{border-color:#89b4fa;}")
        self.edit_value.setPlaceholderText("Digite o novo valor...")
        row1.addWidget(self.edit_value)
        input_lay.addLayout(row1)

        # Linha 2: substituir por (só no modo replace)
        row2 = QHBoxLayout()
        self.lbl_replace = QLabel("Substituir por:")
        self.lbl_replace.setFixedWidth(100)
        self.lbl_replace.setStyleSheet("color:#a6adc8; font-size:12px;")
        row2.addWidget(self.lbl_replace)

        self.edit_replace = QLineEdit()
        self.edit_replace.setFixedHeight(34)
        self.edit_replace.setStyleSheet(
            "QLineEdit{font-size:13px;background:#26263a;color:#cdd6f4;"
            "border:1px solid #45475a;border-radius:5px;padding:2px 10px;}")
        self.edit_replace.setPlaceholderText("Novo texto (deixe vazio para remover)")
        row2.addWidget(self.edit_replace)
        input_lay.addLayout(row2)

        body_lay.addWidget(self.input_group)

        # Preview da operação
        self.preview_lbl = QLabel("")
        self.preview_lbl.setStyleSheet(
            "color:#a6e3a1; font-size:12px; font-family:Consolas;"
            "background:#0d1a0d; padding:8px 12px; border-radius:5px;"
            "border:1px solid #1a4e1a;")
        self.preview_lbl.setWordWrap(True)
        body_lay.addWidget(self.preview_lbl)

        body_lay.addStretch()
        scroll = wrap_widget_in_scroll_area(body, self)
        layout.addWidget(scroll, 1)

        # Conecta preview em tempo real
        self.edit_value.textChanged.connect(self._update_preview)
        self.edit_replace.textChanged.connect(self._update_preview)

        # ── Botões ──
        btn_bar = QWidget()
        btn_bar.setFixedHeight(52)
        btn_bar.setStyleSheet(
            "background:#181825; border-top:1px solid #313244;")
        b_lay = QHBoxLayout(btn_bar)
        b_lay.setContentsMargins(16, 8, 16, 8)
        b_lay.setSpacing(8)
        b_lay.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        b_lay.addWidget(btn_cancel)

        self.btn_apply = QPushButton("▶  Aplicar em Lote")
        self.btn_apply.setFixedHeight(34)
        self.btn_apply.setMinimumWidth(180)
        self.btn_apply.setStyleSheet(
            "QPushButton{"
            "  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "    stop:0 #40c878,stop:1 #2ea85a);"
            "  color:#001a0a;border:none;border-radius:6px;"
            "  font-size:13px;font-weight:800;padding:0 16px;"
            "}"
            "QPushButton:hover{background:#52e890;}")
        self.btn_apply.clicked.connect(self._apply)
        b_lay.addWidget(self.btn_apply)

        layout.addWidget(btn_bar)

        self._update_inputs()
        self._update_preview()

    def _make_rb(self, text: str, tooltip: str, checked: bool = False):
        from PyQt6.QtWidgets import QRadioButton
        rb = QRadioButton(text)
        rb.setChecked(checked)
        rb.setToolTip(tooltip)
        rb.setStyleSheet(
            "QRadioButton{color:#cdd6f4;font-size:12px;padding:2px 4px;}"
            "QRadioButton:checked{color:#cba6f7;font-weight:700;}"
            "QRadioButton:hover{color:white;}")
        return rb

    def _update_inputs(self):
        mode = self._get_mode()
        is_clear = (mode == 'clear')
        is_replace = (mode == 'replace')

        self.input_group.setVisible(not is_clear)
        self.lbl_replace.setVisible(is_replace)
        self.edit_replace.setVisible(is_replace)

        if mode == 'set':
            self.lbl_val.setText("Novo valor:")
            self.edit_value.setPlaceholderText("Digite o valor que todas as linhas receberão...")
        elif mode == 'replace':
            self.lbl_val.setText("Localizar:")
            self.edit_value.setPlaceholderText("Texto a localizar em cada campo...")
        elif mode == 'prefix':
            self.lbl_val.setText("Prefixo:")
            self.edit_value.setPlaceholderText("Texto a adicionar no início...")
        elif mode == 'suffix':
            self.lbl_val.setText("Sufixo:")
            self.edit_value.setPlaceholderText("Texto a adicionar no final...")

        self._update_preview()

    def _get_mode(self) -> str:
        if self.rb_clear.isChecked():
            return 'clear'
        if self.rb_replace.isChecked():
            return 'replace'
        if self.rb_prefix.isChecked():
            return 'prefix'
        if self.rb_suffix.isChecked():
            return 'suffix'
        return 'set'

    def _update_preview(self):
        mode = self._get_mode()
        val = self.edit_value.text()
        rep = self.edit_replace.text()
        sample = self.current_sample or 'VALOR_ATUAL'

        if mode == 'set':
            result = val or '(vazio)'
            desc = f"Todas as {self.row_count:,} linhas receberão: '{result}'"
        elif mode == 'clear':
            result = ''
            desc = f"Todas as {self.row_count:,} linhas terão o campo limpo (valor vazio)"
        elif mode == 'replace':
            if val:
                result = sample.replace(val, rep)
                desc = f"'{sample}' → '{result}'"
            else:
                desc = "Digite o texto a localizar..."
                result = sample
        elif mode == 'prefix':
            result = val + sample
            desc = f"'{sample}' → '{result}'"
        elif mode == 'suffix':
            result = sample + val
            desc = f"'{sample}' → '{result}'"
        else:
            desc = ''

        self.preview_lbl.setText(f"Preview: {desc}")

    def _apply(self):
        mode = self._get_mode()
        self._mode = mode

        if mode == 'set':
            self._result_value = self.edit_value.text()
        elif mode == 'clear':
            self._result_value = ''
        elif mode == 'replace':
            if not self.edit_value.text():
                QMessageBox.warning(self, "Atenção", "Digite o texto a localizar.")
                return
            self._result_value = f'__REPLACE__{self.edit_value.text()}__WITH__{self.edit_replace.text()}'
        elif mode == 'prefix':
            self._result_value = f'__PREFIX__{self.edit_value.text()}'
        elif mode == 'suffix':
            self._result_value = f'__SUFFIX__{self.edit_value.text()}'

        self.accept()

    def get_result(self) -> tuple:
        """Retorna (mode, value) para aplicar."""
        return self._mode, self._result_value

    def compute_new_value(self, current_val: str) -> str:
        """Calcula o valor final para uma linha com base no modo selecionado."""
        mode = self._mode
        val = self._result_value or ''

        if mode == 'set':
            return val
        if mode == 'clear':
            return ''
        if mode == 'replace':
            # formato: __REPLACE__localizar__WITH__substituir
            parts = val.split('__WITH__', 1)
            find = parts[0].replace('__REPLACE__', '', 1)
            repl = parts[1] if len(parts) > 1 else ''
            return current_val.replace(find, repl)
        if mode == 'prefix':
            prefix = val.replace('__PREFIX__', '', 1)
            return prefix + current_val
        if mode == 'suffix':
            suffix = val.replace('__SUFFIX__', '', 1)
            return current_val + suffix
        return current_val
