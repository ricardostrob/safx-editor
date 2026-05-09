"""Utilitários de janela (minimizar / maximizar em diálogos)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QWidget, QScrollArea, QSizePolicy


def enable_dialog_min_max(dialog: QDialog) -> None:
    """
    Garante botões minimizar e maximizar sem substituir o tipo de janela inteiro
    (melhor compatibilidade com Windows / Qt 6).
    """
    dialog.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
    dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
    dialog.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, True)


def wrap_widget_in_scroll_area(
    content: QWidget,
    parent: QWidget | None = None,
) -> QScrollArea:
    """
    Envolve um widget em QScrollArea com rolagem vertical (e horizontal se preciso).
    Use no corpo de diálogos densos para caber em telas baixas / zoom alto.
    """
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(content)
    content.setMinimumWidth(280)
    scroll.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )
    return scroll
