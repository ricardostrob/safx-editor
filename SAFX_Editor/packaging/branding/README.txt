Coloque aqui um ficheiro **logo.png** (ou **logo.jpg**) quadrado, ≥256 px, com a logotipo da empresa.
O script `build_assets.py` usa isto no assistente Inno (Windows) e no fundo do DMG (macOS).

Se não existir logo, é usado texto "SAFX Editor" / "Adejo Tecnologia" sobre o fundo azul escuro da marca.

Gerar manualmente (na pasta SAFX_Editor):

    python packaging/branding/build_assets.py --inno-only
    python packaging/branding/build_assets.py --dmg-only
