#!/usr/bin/env python3
"""
SAFX Editor — gera DMG no Mac.

USO (no Terminal):
    python3 build_dmg_mac.py

Não precisa de chmod, não precisa de duplo clique em .command.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list, **kw) -> None:
    print("+", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        print(f"\n[ERRO] Comando falhou (código {r.returncode})", file=sys.stderr)
        sys.exit(r.returncode)


def main() -> int:
    if sys.platform != "darwin":
        print("Este script só corre no macOS. No Mac, execute:")
        print('  python3 build_dmg_mac.py')
        return 2

    root = Path(__file__).resolve().parent
    os.chdir(root)

    # Garante que Homebrew e Python instalados via brew estão no PATH
    os.environ["PATH"] = (
        "/opt/homebrew/bin:/opt/homebrew/sbin:"
        "/usr/local/bin:/usr/local/sbin:"
        "/usr/bin:/usr/sbin:/bin:/sbin:"
    ) + os.environ.get("PATH", "")

    print("=" * 60)
    print("  SAFX Editor — Build DMG")
    print("=" * 60)
    print(f"  Pasta: {root}")
    print(f"  Python: {sys.executable} ({sys.version.split()[0]})")

    # ── pip install ──────────────────────────────────────────
    print("\n[1/4] Instalando dependências...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt",
         "-r", "packaging/requirements-build.txt", "--quiet"])

    # ── PyInstaller ─────────────────────────────────────────
    print("\n[2/4] Compilando .app com PyInstaller (pode demorar)...")
    run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "SAFX_Editor.spec"])

    app = root / "dist" / "SAFX_Editor.app"
    if not app.is_dir():
        dist = root / "dist"
        files = list(dist.iterdir()) if dist.is_dir() else []
        print(f"[ERRO] .app não gerado em {app}", file=sys.stderr)
        print(f"       Conteúdo de dist/: {files}", file=sys.stderr)
        return 1

    # ── Codesign opcional ────────────────────────────────────
    ident = os.environ.get("CODESIGN_IDENTITY", "").strip()
    if ident:
        print("\n[2.5] Assinando .app...")
        run(["codesign", "--force", "--deep", "--sign", ident, str(app)])

    # ── Montar DMG ───────────────────────────────────────────
    print("\n[3/4] Criando DMG...")
    release = root / "release"
    release.mkdir(exist_ok=True)
    dmg = release / "SAFX_Editor_macos.dmg"
    dmg.unlink(missing_ok=True)

    desinst = root / "packaging" / "macos" / "Desinstalar_SAFX_Editor.command"

    stage = Path(tempfile.mkdtemp(prefix="safx_dmg_"))
    try:
        shutil.copytree(app, stage / "SAFX_Editor.app", symlinks=True)
        os.symlink("/Applications", stage / "Applications")
        if desinst.is_file():
            dst = stage / "Desinstalar_SAFX_Editor.command"
            shutil.copy2(desinst, dst)
            os.chmod(dst, 0o755)

        subprocess.run(
            [
                "hdiutil", "create",
                "-volname", "SAFX Editor",
                "-srcfolder", str(stage),
                "-ov", "-format", "UDZO",
                str(dmg),
            ],
            check=True,
        )
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    if not dmg.is_file():
        print("[ERRO] hdiutil não criou o DMG.", file=sys.stderr)
        return 1

    # ── Copiar para Macbook/ ─────────────────────────────────
    print("\n[4/4] Copiando DMG para Macbook/...")
    macbook = root.parent / "Macbook"
    macbook.mkdir(exist_ok=True)
    dst_dmg = macbook / dmg.name
    shutil.copy2(dmg, dst_dmg)

    print("\n" + "=" * 60)
    print("  PRONTO!")
    print(f"  DMG: {dst_dmg}")
    print("  Envie este ficheiro para o cliente.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
