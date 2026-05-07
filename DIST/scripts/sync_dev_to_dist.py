"""
Script de sincronização DEV → DIST.
Copia automaticamente todos os arquivos do desenvolvimento para a pasta de distribuição.
Execute após qualquer alteração no código para manter o pacote do cliente atualizado.

Uso:
    python sync_dev_to_dist.py
    python sync_dev_to_dist.py --watch   # monitora e sincroniza automaticamente
"""
import os
import sys
import shutil
import hashlib
import time
import argparse
from pathlib import Path

BASE = Path(__file__).parent.parent.parent  # DEV/LANXESS
SRC = BASE / "SAFX_Editor"
DST = BASE / "DIST" / "SAFX_Editor"

EXCLUDE_DIRS = {'__pycache__', '.git', 'dist', 'build', '.pytest_cache', 'venv', '.venv'}
EXCLUDE_EXTS = {'.pyc', '.pyo', '.log', '.tmp', '.db'}
EXCLUDE_FILES = {'.keystore', 'config.json'}


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def should_exclude(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    if path.suffix in EXCLUDE_EXTS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    return False


def sync(verbose: bool = True) -> tuple:
    copied = 0
    skipped = 0
    errors = []

    DST.mkdir(parents=True, exist_ok=True)

    # Copia arquivos SRC → DST
    for src_file in SRC.rglob('*'):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(SRC)
        if should_exclude(rel):
            continue

        dst_file = DST / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)

        # Compara hash — só copia se mudou
        if dst_file.exists() and file_hash(src_file) == file_hash(dst_file):
            skipped += 1
            continue

        try:
            shutil.copy2(src_file, dst_file)
            if verbose:
                print(f"  ✓ {rel}")
            copied += 1
        except Exception as e:
            errors.append(f"ERRO {rel}: {e}")

    # Copia LICENSE
    lic_src = BASE / "LICENSE"
    lic_dst = BASE / "DIST" / "LICENSE"
    if lic_src.exists():
        shutil.copy2(lic_src, lic_dst)

    return copied, skipped, errors


def watch_mode():
    print("👁  Modo watch ativo — sincronizando automaticamente ao detectar mudanças...")
    print("   Pressione Ctrl+C para parar.\n")
    last_sync = {}

    while True:
        changed = False
        for src_file in SRC.rglob('*.py'):
            rel = src_file.relative_to(SRC)
            if should_exclude(rel):
                continue
            mtime = src_file.stat().st_mtime
            if last_sync.get(str(rel)) != mtime:
                last_sync[str(rel)] = mtime
                changed = True

        if changed:
            ts = time.strftime('%H:%M:%S')
            print(f"\n[{ts}] Alterações detectadas — sincronizando...")
            copied, skipped, errors = sync(verbose=False)
            print(f"  ✓ {copied} arquivo(s) copiado(s), {skipped} sem mudança")
            for err in errors:
                print(f"  ✗ {err}")

        time.sleep(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sync DEV → DIST')
    parser.add_argument('--watch', action='store_true',
                        help='Monitorar e sincronizar automaticamente')
    args = parser.parse_args()

    print(f"\nSAFX Editor — Sync DEV → DIST")
    print(f"Origem : {SRC}")
    print(f"Destino: {DST}\n")

    if args.watch:
        try:
            watch_mode()
        except KeyboardInterrupt:
            print("\nWatch encerrado.")
    else:
        copied, skipped, errors = sync()
        print(f"\n✓ Concluído: {copied} arquivo(s) copiado(s), {skipped} sem mudança")
        if errors:
            print("\nErros:")
            for e in errors:
                print(f"  {e}")
