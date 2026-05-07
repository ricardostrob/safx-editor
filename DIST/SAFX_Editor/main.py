"""
SAFX Editor — MasterSAF Data Adjuster
Ponto de entrada principal.

Uso:
    python main.py [--layout-dir "caminho/para/MANUAL LAYOUT"]

Requisitos:
    pip install PyQt6

Compatível com: Windows 10/11, macOS, Linux
"""
import sys
import os
import logging
import argparse
from pathlib import Path

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Garante que o pacote seja encontrado quando executado diretamente
_THIS_DIR = Path(__file__).parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))


def main():
    parser = argparse.ArgumentParser(
        description="SAFX Editor — MasterSAF Data Adjuster")
    parser.add_argument(
        '--layout-dir', '-l',
        default=None,
        help='Diretório com os arquivos MD do MANUAL LAYOUT')
    args = parser.parse_args()

    # Determina diretório de layouts
    layout_dir = args.layout_dir

    # Se não especificado, tenta encontrar automaticamente
    if not layout_dir:
        candidates = [
            _THIS_DIR.parent / "MANUAL LAYOUT",   # pasta pai do projeto
            _THIS_DIR / "MANUAL LAYOUT",           # dentro do projeto
            Path.cwd() / "MANUAL LAYOUT",          # diretório atual
        ]
        for candidate in candidates:
            if candidate.exists():
                layout_dir = str(candidate)
                logger.info(f"MANUAL LAYOUT encontrado: {layout_dir}")
                break
        else:
            logger.warning(
                "Diretório MANUAL LAYOUT não encontrado automaticamente. "
                "Configure manualmente em Arquivo > Configurar Diretório de Layouts.")

    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
    except ImportError:
        print("ERRO: PyQt6 não está instalado.")
        print("Execute: pip install PyQt6")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("SAFX Editor")
    app.setOrganizationName("LANXESS Brasil")
    app.setApplicationVersion("1.0.0")

    # Fonte padrão
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Suporte a HiDPI
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    except AttributeError:
        pass

    from ui.main_window import MainWindow
    window = MainWindow(layout_dir=layout_dir)
    window.show()

    logger.info("SAFX Editor iniciado")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
