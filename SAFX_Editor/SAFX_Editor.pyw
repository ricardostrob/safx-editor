"""
SAFX Editor - Launcher
Executado pelo pythonw.exe (sem janela de terminal)
Duplo-clique direto ou via atalho com icone.
"""
import sys
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))

# Garante que o diretório do projeto está no PYTHONPATH
if BASE not in sys.path:
    sys.path.insert(0, BASE)

# Verifica/instala dependências silenciosamente
def _ensure(pkg, import_name=None):
    try:
        __import__(import_name or pkg)
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            capture_output=True
        )

_ensure("PyQt6")
_ensure("flask")
_ensure("paramiko")

# Detecta layout dir
layout_candidates = [
    os.path.join(BASE, "..", "MANUAL LAYOUT"),
    os.path.join(BASE, "..", "ESTRUTURA", "estrutura_md"),
    os.path.join(BASE, "MANUAL LAYOUT"),
]
layout_dir = None
for c in layout_candidates:
    if os.path.isdir(c):
        layout_dir = os.path.normpath(c)
        break

# Injeta argumento para main.py
if layout_dir:
    sys.argv = [sys.argv[0], "--layout-dir", layout_dir]

# Lança a aplicação
from main import main
main()
