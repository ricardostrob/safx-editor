#!/usr/bin/env bash
# Encaminha para o fluxo em Python (não depende de chmod +x nos .command do Finder).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/build_dmg_mac.py"
