"""
Gera artefactos gráficos para instaladores (Inno Setup + fundo DMG opcional).
Executar a partir da pasta SAFX_Editor:  python packaging/branding/build_assets.py

Opcional: packaging/branding/logo.png (PNG, ≥256px recomendado) para a sua marca.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

BRAND_BG = (14, 27, 46)  # #0e1b2e
ACCENT = (137, 180, 250)
TEXT_LIGHT = (230, 235, 245)

HERE = Path(__file__).resolve().parent
OUT = HERE
LOGO_CANDIDATES = (OUT / "logo.png", OUT / "logo.jpg")


def _solid_bmp(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    """BMP 24-bit; primeira linha no ficheiro = linha inferior da imagem (ordem BMP)."""
    b, g, r = rgb[2], rgb[1], rgb[0]
    row_stride = (width * 3 + 3) // 4 * 4
    pad = row_stride - width * 3
    line = bytes([b, g, r]) * width + b"\x00" * pad
    body = line * height
    header_size = 14 + 40
    image_size = len(body)
    file_size = header_size + image_size
    header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, header_size)
    dib = struct.pack(
        "<IiiHHIIIIII",
        40,
        width,
        height,
        1,
        24,
        0,
        image_size,
        0,
        0,
        0,
        0,
    )
    path.write_bytes(header + dib + body)


def _with_pillow() -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401

        return True
    except ImportError:
        return False


def _load_logo():
    from PIL import Image

    for p in LOGO_CANDIDATES:
        if p.is_file():
            return Image.open(p).convert("RGBA")
    return None


def _font(size: int):
    from PIL import ImageFont

    paths = (
        "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    )
    for p in paths:
        try:
            return ImageFont.truetype(p, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_inno_images() -> None:
    w_large, h_large = 164, 314
    w_small, h_small = 55, 58

    if not _with_pillow():
        _solid_bmp(OUT / "wizard_large.bmp", w_large, h_large, BRAND_BG)
        _solid_bmp(OUT / "wizard_small.bmp", w_small, h_small, BRAND_BG)
        print(
            "Pillow ausente: BMPs sólidos. Instale Pillow para logo/texto: pip install pillow",
            file=sys.stderr,
        )
        return

    from PIL import Image, ImageDraw

    def text_size(dr: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
        bbox = dr.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    # Painel grande (lateral do assistente Inno)
    im_l = Image.new("RGB", (w_large, h_large), BRAND_BG)
    dr = ImageDraw.Draw(im_l)
    logo = _load_logo()
    if logo:
        side = min(int(w_large * 0.72), int(h_large * 0.42))
        lg = logo.resize((side, side), Image.Resampling.LANCZOS)
        lx = (w_large - side) // 2
        ly = int(h_large * 0.10)
        im_l.paste(lg, (lx, ly), lg)
        y0 = ly + side + int(h_large * 0.05)
    else:
        y0 = int(h_large * 0.16)
    font_title = _font(max(14, w_large // 11))
    font_sub = _font(max(9, w_large // 18))
    title = "SAFX Editor"
    sub = "Adejo Tecnologia / TecTex"
    tw, th = text_size(dr, title, font_title)
    dr.text(((w_large - tw) // 2, y0), title, fill=TEXT_LIGHT, font=font_title)
    sw, sh = text_size(dr, sub, font_sub)
    dr.text(((w_large - sw) // 2, y0 + th + 6), sub, fill=ACCENT, font=font_sub)
    im_l.save(OUT / "wizard_large.bmp", format="BMP")

    # Painel pequeno (canto do assistente)
    im_s = Image.new("RGB", (w_small, h_small), BRAND_BG)
    drs = ImageDraw.Draw(im_s)
    drs.rectangle((0, 0, w_small, 6), fill=ACCENT)
    if logo:
        lg2 = logo.resize((40, 40), Image.Resampling.LANCZOS)
        im_s.paste(lg2, ((w_small - 40) // 2, 10), lg2)
    im_s.save(OUT / "wizard_small.bmp", format="BMP")

    # Ícone do Setup.exe
    ico_base = Image.new("RGBA", (256, 256), BRAND_BG + (255,))
    logo = _load_logo()
    if logo:
        lg = logo.resize((200, 200), Image.Resampling.LANCZOS)
        ico_base.paste(lg, (28, 28), lg)
    else:
        dr2 = ImageDraw.Draw(ico_base)
        f = _font(40)
        dr2.text((48, 96), "SAFX", fill=TEXT_LIGHT, font=f)
    ico_base.resize((256, 256), Image.Resampling.LANCZOS).save(
        OUT / "setup.ico", format="ICO", sizes=[(256, 256)]
    )
    print("Inno: wizard_large.bmp, wizard_small.bmp, setup.ico →", OUT)


def build_dmg_background() -> None:
    w, h = 600, 400
    if not _with_pillow():
        print(
            "Pillow ausente: dmg_background.png não gerado.",
            file=sys.stderr,
        )
        return
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), BRAND_BG)
    dr = ImageDraw.Draw(im)
    logo = _load_logo()
    if logo:
        side = 160
        lg = logo.resize((side, side), Image.Resampling.LANCZOS)
        im.paste(lg, ((w - side) // 2, 60), lg)
    font_t = _font(26)
    font_s = _font(15)
    dr.text((w // 2 - 110, 250), "SAFX Editor", fill=TEXT_LIGHT, font=font_t)
    dr.text(
        (w // 2 - 220, 290),
        "Arraste SAFX_Editor.app para Aplicativos →",
        fill=ACCENT,
        font=font_s,
    )
    im.save(OUT / "dmg_background.png", format="PNG")
    print("DMG: dmg_background.png →", OUT)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    argv = [a.lower() for a in sys.argv[1:]]
    if "--dmg-only" in argv:
        build_dmg_background()
        return 0
    if "--inno-only" in argv:
        build_inno_images()
        return 0
    build_inno_images()
    build_dmg_background()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
