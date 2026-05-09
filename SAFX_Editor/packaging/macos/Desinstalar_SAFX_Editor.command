#!/bin/bash
# Remove o app de /Applications e dados em ~/.safx_editor (com confirmação).
set -e
APP="/Applications/SAFX_Editor.app"
CFG="$HOME/.safx_editor"

RESP=$(osascript -e 'button returned of (display dialog "Remover SAFX Editor de Aplicativos e apagar configuracoes em ~/.safx_editor ?" buttons {"Cancelar", "Remover"} default button "Remover" with title "Desinstalar SAFX Editor")')

if [[ "$RESP" != "Remover" ]]; then
  exit 0
fi

if [[ -d "$APP" ]]; then
  rm -rf "$APP"
fi
if [[ -d "$CFG" ]]; then
  rm -rf "$CFG"
fi

osascript -e 'display notification "SAFX Editor foi removido." with title "SAFX Editor"' 2>/dev/null || true
