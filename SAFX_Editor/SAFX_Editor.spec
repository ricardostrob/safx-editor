# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller - SAFX Editor (Windows .exe + pasta / macOS .app).
Executar na pasta SAFX_Editor: pyinstaller --clean --noconfirm SAFX_Editor.spec
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
ROOT = Path(SPECPATH)

# UPX desligado: causa falhas no macOS e inconsistencias no Windows.
_USE_UPX = False

# Arch definida pelo interpretador Python usado: x86_64 via Rosetta ou arm64 nativo.
_TARGET_ARCH = None

hiddenimports = collect_submodules("ui") + collect_submodules("core")
hiddenimports += [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtPrintSupport",
    "flask",
    "flask_cors",
    "werkzeug",
    "jinja2",
    "itsdangerous",
    "click",
    "blinker",
    "paramiko",
    "cryptography",
    "bcrypt",
    "nacl",
    "openpyxl",
    "et_xmlfile",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "resources"), "resources")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "scipy", "PIL", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SAFX_Editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=_USE_UPX,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=_TARGET_ARCH,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=_USE_UPX,
    upx_exclude=[],
    name="SAFX_Editor",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SAFX_Editor.app",
        bundle_identifier="com.adejo.safxeditor",
        version="1.0.0",
        info_plist={
            "NSPrincipalClass": "NSApplication",
            "NSHighResolutionCapable": True,
            "CFBundleName": "SAFX Editor",
            "CFBundleDisplayName": "SAFX Editor",
            "CFBundleShortVersionString": "1.0.0",
        },
    )
