"""
Diálogo de progresso de importação — design moderno com métricas em tempo real.
"""
import time
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QProgressBar, QFrame
)


class AnimatedProgressBar(QProgressBar):
    """Barra de progresso com gradiente animado e efeito de brilho."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim_offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)   # ~25fps

    def _tick(self):
        self._anim_offset = (self._anim_offset + 3) % 60
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        # Sobrepõe um brilho deslizante se em andamento
        if 0 < self.value() < self.maximum() or self.maximum() == 0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = self.width()
            h = self.height()
            if self.maximum() > 0:
                fill_w = int(w * self.value() / self.maximum())
            else:
                fill_w = w

            # Brilho deslizante
            shine_x = (self._anim_offset * fill_w // 60) - 20
            from PyQt6.QtGui import QLinearGradient
            grad = QLinearGradient(shine_x, 0, shine_x + 40, 0)
            grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            grad.setColorAt(0.5, QColor(255, 255, 255, 60))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(0, 0, min(fill_w, w), h, grad)
            painter.end()


class ImportProgressDialog(QDialog):
    """
    Diálogo moderno de progresso de importação com:
    - Barra animada com métricas em tempo real
    - Velocidade de linhas/segundo
    - Tempo estimado restante
    - Log de mensagens recentes
    """

    cancelRequested = pyqtSignal()

    def __init__(self, table_name: str, parent=None, theme: str = 'dark'):
        super().__init__(parent)
        self.table_name = table_name
        self.theme = theme
        self._start_time = time.time()
        self._last_count = 0
        self._last_time = time.time()
        self._speed_samples = []   # últimas N velocidades para média móvel
        self._total_known = 0
        self._cancelled = False

        self.setWindowTitle("Importando SAFX")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMinimumSize(520, 320)
        self.setModal(True)
        self._apply_theme()
        self._setup_ui()

        # Timer para atualizar métricas de velocidade
        self._metrics_timer = QTimer(self)
        self._metrics_timer.timeout.connect(self._update_speed)
        self._metrics_timer.start(500)

    def _apply_theme(self):
        if self.theme == 'light':
            self.setStyleSheet("""
                QDialog { background: #f5f5f0; color: #1a1a2e; }
                QLabel  { color: #1a1a2e; }
                QPushButton {
                    background: #e0e0e8; color: #1a1a2e;
                    border: 1px solid #b0b0c0; border-radius: 6px;
                    padding: 6px 18px; font-weight: 700;
                }
                QPushButton:hover { background: #ff6b6b; color: white; border-color: #ff6b6b; }
                QProgressBar {
                    background: #dde1e7; border: none; border-radius: 6px; height: 14px;
                }
                QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4a90d9, stop:1 #67b7f7); border-radius: 6px; }
                QFrame#logFrame { background: #e8eaf0; border-radius: 6px; border: 1px solid #c0c4d0; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background: #12121e; color: #cdd6f4; }
                QLabel  { color: #cdd6f4; }
                QPushButton {
                    background: #2a1a1a; color: #f38ba8;
                    border: 1px solid #4a2a2a; border-radius: 6px;
                    padding: 6px 18px; font-weight: 700;
                }
                QPushButton:hover { background: #f38ba8; color: #1e1e2e; }
                QProgressBar {
                    background: #26263a; border: none; border-radius: 7px; height: 14px;
                }
                QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #89b4fa, stop:1 #cba6f7); border-radius: 7px; }
                QFrame#logFrame { background: #1a1a2e; border-radius: 6px; border: 1px solid #313244; }
            """)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header colorido ──
        if self.theme == 'light':
            hdr_bg = "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4a90d9,stop:1 #67b7f7);"
            hdr_fg = "color: white;"
        else:
            hdr_bg = "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1a1a2e,stop:1 #2a1a3e);"
            hdr_fg = "color: #cba6f7;"

        header = QWidget()
        header.setFixedHeight(58)
        header.setStyleSheet(f"{hdr_bg} border-bottom: 2px solid #313244;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 0, 20, 0)

        icon_lbl = QLabel("⬆")
        icon_lbl.setStyleSheet(f"font-size: 22px; {hdr_fg}")
        h_lay.addWidget(icon_lbl)

        title = QLabel(f"  Importando  {self.table_name}")
        title.setStyleSheet(f"font-size: 15px; font-weight: 800; letter-spacing: 0.5px; {hdr_fg}")
        h_lay.addWidget(title)
        h_lay.addStretch()

        self.lbl_count_hdr = QLabel("preparando…")
        self.lbl_count_hdr.setStyleSheet(f"font-size: 12px; opacity: 0.8; {hdr_fg}")
        h_lay.addWidget(self.lbl_count_hdr)

        root.addWidget(header)

        # ── Corpo ──
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 16, 24, 12)
        body_lay.setSpacing(10)

        # Mensagem de status
        self.lbl_status = QLabel("Lendo arquivo…")
        self.lbl_status.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.lbl_status.setWordWrap(True)
        body_lay.addWidget(self.lbl_status)

        # Barra de progresso
        self.progress_bar = AnimatedProgressBar()
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        body_lay.addWidget(self.progress_bar)

        # Métricas em tempo real
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(24)

        self.lbl_pct = self._metric_label("0%", big=True)
        metrics_row.addWidget(self.lbl_pct)

        self.lbl_lines = self._metric_label("— linhas", sub="carregadas")
        metrics_row.addWidget(self.lbl_lines)

        self.lbl_speed = self._metric_label("— /s", sub="linhas/seg")
        metrics_row.addWidget(self.lbl_speed)

        self.lbl_eta = self._metric_label("—", sub="tempo restante")
        metrics_row.addWidget(self.lbl_eta)

        self.lbl_elapsed = self._metric_label("0s", sub="decorrido")
        metrics_row.addWidget(self.lbl_elapsed)

        metrics_row.addStretch()
        body_lay.addLayout(metrics_row)

        # Log de mensagens recentes
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244; margin: 4px 0;")
        body_lay.addWidget(sep)

        log_frame = QFrame()
        log_frame.setObjectName("logFrame")
        log_frame.setFixedHeight(80)
        log_lay = QVBoxLayout(log_frame)
        log_lay.setContentsMargins(10, 6, 10, 6)
        log_lay.setSpacing(2)

        self._log_labels = []
        for _ in range(3):
            lbl = QLabel("")
            lbl.setStyleSheet("font-size: 11px; font-family: Consolas; opacity: 0.7;")
            lbl.setWordWrap(True)
            log_lay.addWidget(lbl)
            self._log_labels.append(lbl)

        body_lay.addWidget(log_frame)
        body_lay.addStretch()

        root.addWidget(body, 1)

        # ── Rodapé ──
        footer = QWidget()
        footer.setFixedHeight(50)
        footer.setStyleSheet("border-top: 1px solid #313244;")
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(20, 8, 20, 8)

        self.lbl_file_info = QLabel("")
        self.lbl_file_info.setStyleSheet("font-size: 11px; opacity: 0.6;")
        f_lay.addWidget(self.lbl_file_info)
        f_lay.addStretch()

        self.btn_cancel = QPushButton("✕  Cancelar")
        self.btn_cancel.setFixedHeight(32)
        self.btn_cancel.setFixedWidth(110)
        self.btn_cancel.clicked.connect(self._on_cancel)
        f_lay.addWidget(self.btn_cancel)

        root.addWidget(footer)

    def _metric_label(self, value: str, sub: str = "", big: bool = False) -> QWidget:
        """Cria um par (valor, label) para a linha de métricas."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        val_lbl = QLabel(value)
        size = "18px" if big else "14px"
        val_lbl.setStyleSheet(f"font-size: {size}; font-weight: 800; color: #89b4fa;")
        lay.addWidget(val_lbl)

        if sub:
            sub_lbl = QLabel(sub)
            sub_lbl.setStyleSheet("font-size: 10px; opacity: 0.5;")
            lay.addWidget(sub_lbl)

        w._val_lbl = val_lbl
        return w

    def _set_metric(self, widget: QWidget, text: str):
        widget._val_lbl.setText(text)

    def _on_cancel(self):
        self._cancelled = True
        self.cancelRequested.emit()
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelando…")
        self.lbl_status.setText("Cancelando importação…")

    def set_file_info(self, path: str):
        """Exibe nome do arquivo no rodapé."""
        from pathlib import Path
        self.lbl_file_info.setText(f"📄 {Path(path).name}")

    def update_progress(self, pct: int, message: str):
        """Atualiza percentual, mensagem e log."""
        self.progress_bar.setValue(max(0, min(100, pct)))
        self.lbl_status.setText(message)
        self._set_metric(self.lbl_pct, f"{pct}%")

        # Extrai contagem de linhas da mensagem
        import re
        m = re.search(r'([\d,\.]+)\s*linha', message, re.IGNORECASE)
        if m:
            raw = m.group(1).replace('.', '').replace(',', '')
            try:
                count = int(raw)
                self._update_count(count)
            except ValueError:
                pass

        # Adiciona ao log visual
        self._push_log(message)

        # Atualiza header
        self.lbl_count_hdr.setText(f"{pct}% concluído")

    def _update_count(self, count: int):
        self._set_metric(self.lbl_lines, f"{count:,}")
        now = time.time()
        elapsed = now - self._start_time

        delta_t = now - self._last_time
        delta_n = count - self._last_count

        if delta_t > 0.4 and delta_n > 0:
            speed = delta_n / delta_t
            self._speed_samples.append(speed)
            if len(self._speed_samples) > 6:
                self._speed_samples.pop(0)
            avg_speed = sum(self._speed_samples) / len(self._speed_samples)

            self._set_metric(self.lbl_speed, f"{avg_speed:,.0f}/s")

            if self._total_known > count and avg_speed > 0:
                remaining_lines = self._total_known - count
                eta_sec = remaining_lines / avg_speed
                self._set_metric(self.lbl_eta, _fmt_time(eta_sec))
            else:
                self._set_metric(self.lbl_eta, "—")

            self._last_time = now
            self._last_count = count

        self._set_metric(self.lbl_elapsed, _fmt_time(elapsed))

    def _update_speed(self):
        """Atualiza tempo decorrido periodicamente."""
        elapsed = time.time() - self._start_time
        self._set_metric(self.lbl_elapsed, _fmt_time(elapsed))

    def _push_log(self, msg: str):
        """Desloca as mensagens de log."""
        msgs = [lbl.text() for lbl in self._log_labels]
        msgs.append(f"  {msg}")
        msgs = msgs[-3:]
        for lbl, txt in zip(self._log_labels, msgs):
            lbl.setText(txt)

    def mark_done(self, count: int, table_name: str):
        """Marca como concluído."""
        elapsed = time.time() - self._start_time
        self.progress_bar.setValue(100)
        self._set_metric(self.lbl_pct, "100%")
        self._set_metric(self.lbl_lines, f"{count:,}")
        self._set_metric(self.lbl_eta, "✓")
        self._set_metric(self.lbl_elapsed, _fmt_time(elapsed))
        speed = count / elapsed if elapsed > 0 else 0
        self._set_metric(self.lbl_speed, f"{speed:,.0f}/s")
        self.lbl_status.setText(
            f"✓  {count:,} registros importados em {_fmt_time(elapsed)}")
        self.lbl_count_hdr.setText(f"Concluído — {count:,} linhas")
        self.btn_cancel.setText("  Fechar")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.accept)
        self._metrics_timer.stop()


def _fmt_time(secs: float) -> str:
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"
