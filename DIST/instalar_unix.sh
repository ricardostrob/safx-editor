#!/usr/bin/env bash
# SAFX Editor — Instalação para macOS / Linux
# Adejo Tecnologia / TecTex  |  (11) 99308-3138

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          SAFX Editor — MasterSAF Data Adjuster          ║"
echo "║       Adejo Tecnologia / TecTex  |  (11) 99308-3138     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Instalando dependências..."
echo ""

# Verifica Python 3
if ! command -v python3 &>/dev/null; then
    echo "[ERRO] Python 3 não encontrado."
    echo "       Instale Python 3.11+ em https://python.org/downloads"
    exit 1
fi

cd "$SCRIPT_DIR/SAFX_Editor"
python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r requirements.txt --quiet

echo ""
echo "✓ Instalação concluída!"
echo ""
echo "Para iniciar o SAFX Editor:"
echo "  python3 '$SCRIPT_DIR/SAFX_Editor/SAFX_Editor.pyw'"
echo ""

# Cria script de inicialização
cat > "$SCRIPT_DIR/iniciar_safx.sh" << EOF
#!/usr/bin/env bash
cd "$SCRIPT_DIR/SAFX_Editor"
python3 SAFX_Editor.pyw &
EOF
chmod +x "$SCRIPT_DIR/iniciar_safx.sh"

echo "Atalho criado: $SCRIPT_DIR/iniciar_safx.sh"
echo ""
echo "Iniciando..."
python3 "$SCRIPT_DIR/SAFX_Editor/SAFX_Editor.pyw" &
