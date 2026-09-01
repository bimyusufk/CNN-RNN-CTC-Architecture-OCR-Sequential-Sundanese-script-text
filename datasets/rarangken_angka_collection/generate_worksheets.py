# -*- coding: utf-8 -*-
"""Generate printable A4 worksheets for hand-collecting the 23 Aksara Sunda
classes with no public dataset: 13 isolated rarangken (diacritic) marks and
10 angka (digit) classes.

Each worksheet page has:
  - a header showing the target class name, its properly-shaped Unicode
    reference glyph (rendered via HarfBuzz+FreeType, since Sundanese
    combining marks need real text shaping, not naive font rendering), and
    a short instruction line;
  - a grid of empty bordered cells to fill by hand, each with a faint index
    label for QC;
  - four solid corner registration squares used by crop_worksheets.py to
    detect and perspective-correct a scanned/photographed page.

Output: datasets/rarangken_angka_collection/worksheets/<class_name>.pdf
(multi-page, one PDF per class)

Usage: python datasets/rarangken_angka_collection/generate_worksheets.py [--pages-per-class N]
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont
Image.init()

from glyph_render import shape_and_render, DOTTED_CIRCLE as DOTTED

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "worksheets")
os.makedirs(OUT_DIR, exist_ok=True)

# (folder_name, unicode_text_to_shape, human label, short description)
RARANGKEN = [
    ("rarangken_panghulu", DOTTED + "\u1ba4", "Panghulu", "mengubah bunyi a -> i"),
    ("rarangken_panyuku", DOTTED + "\u1ba5", "Panyuku", "mengubah bunyi a -> u"),
    ("rarangken_paneuleung", DOTTED + "\u1ba9", "Paneuleung", "mengubah bunyi a -> eu"),
    ("rarangken_paneleng", DOTTED + "\u1ba6", "Panéléng", "mengubah bunyi a -> é"),
    ("rarangken_panolong", DOTTED + "\u1ba7", "Panolong", "mengubah bunyi a -> o"),
    ("rarangken_pamepet", DOTTED + "\u1ba8", "Pamepet", "mengubah bunyi a -> e (pepet)"),
    ("rarangken_panyecek", DOTTED + "\u1b80", "Panyecek", "menambah koda nasal \"ng\""),
    ("rarangken_panglayar", DOTTED + "\u1b81", "Panglayar", "menambah koda \"r\""),
    ("rarangken_pangwisad", DOTTED + "\u1b82", "Pangwisad", "menambah koda \"h\""),
    ("rarangken_pamaeh", DOTTED + "\u1baa", "Pamaéh", "mematikan vokal (klaster/akhir kata)"),
    ("rarangken_pamingkal", DOTTED + "\u1ba1", "Pamingkal", "menyisipkan konsonan medial \"y\""),
    ("rarangken_panyakra", DOTTED + "\u1ba2", "Panyakra", "menyisipkan konsonan medial \"r\""),
    ("rarangken_panyiku", DOTTED + "\u1ba3", "Panyiku", "menyisipkan konsonan medial \"l\""),
]
ANGKA = [
    (f"angka_{d}", chr(0x1BB0 + d), f"Angka {d}", f"aksara angka Sunda untuk {d}")
    for d in range(10)
]
ALL_CLASSES = RARANGKEN + ANGKA

# --- page geometry (300 DPI A4) ---
DPI = 300
PAGE_W, PAGE_H = int(8.27 * DPI), int(11.69 * DPI)
MARGIN = 150
COLS, ROWS = 6, 7
REG_SIZE = 70


def load_font(size, bold=False):
    candidates = (
        ["C:/Windows/Fonts/timesbd.ttf", "C:/Windows/Fonts/arialbd.ttf"] if bold else
        ["C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/arial.ttf"]
    )
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def make_page(class_name, ref_img, label, desc, page_idx, total_pages, cell_start_idx):
    img = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(img)
    f_title = load_font(64, bold=True)
    f_desc = load_font(38)
    f_small = load_font(22)
    f_idx = load_font(18)

    draw.text((MARGIN, 90), f"Lembar Koleksi: {label}", font=f_title, fill="black")
    draw.text((MARGIN, 170), f"({class_name}) \u2014 {desc}", font=f_desc, fill="#333333")
    draw.text((MARGIN, 225),
              f"Halaman {page_idx + 1}/{total_pages}  \u2014  Tulis HANYA bentuk tandanya (jangan tulis huruf dasarnya) di tiap kotak, "
              "gunakan pena hitam, variasikan gaya tulisan tangan.",
              font=f_small, fill="#555555")

    ref_scaled = ref_img.copy()
    ref_h = 190
    ratio = ref_h / ref_scaled.height
    ref_scaled = ref_scaled.resize((max(1, int(ref_scaled.width * ratio)), ref_h))
    ref_x = PAGE_W - MARGIN - ref_scaled.width
    img.paste(ref_scaled, (ref_x, 60), ref_scaled)
    draw.text((ref_x, 60 + ref_h + 4), "acuan bentuk", font=f_small, fill="#888888")

    grid_top = 340
    grid_bottom = PAGE_H - MARGIN
    grid_left = MARGIN
    grid_right = PAGE_W - MARGIN
    cell_w = (grid_right - grid_left) / COLS
    cell_h = (grid_bottom - grid_top) / ROWS

    for (cx, cy) in [(grid_left, grid_top), (grid_right, grid_top),
                      (grid_left, grid_bottom), (grid_right, grid_bottom)]:
        draw.rectangle([cx - REG_SIZE / 2, cy - REG_SIZE / 2, cx + REG_SIZE / 2, cy + REG_SIZE / 2], fill="black")

    idx = cell_start_idx
    for row in range(ROWS):
        for col in range(COLS):
            x0 = grid_left + col * cell_w
            y0 = grid_top + row * cell_h
            x1, y1 = x0 + cell_w, y0 + cell_h
            pad = 10
            draw.rectangle([x0 + pad, y0 + pad, x1 - pad, y1 - pad], outline="#999999", width=2)
            draw.text((x0 + pad + 6, y0 + pad + 4), str(idx), font=f_idx, fill="#bbbbbb")
            idx += 1

    return img


def build_class_worksheet(class_name, unicode_text, label, desc, pages_per_class):
    ref_img = shape_and_render(unicode_text, px_size=260)
    cells_per_page = COLS * ROWS
    pages = []
    cell_idx = 1
    for p in range(pages_per_class):
        page = make_page(class_name, ref_img, label, desc, p, pages_per_class, cell_idx)
        pages.append(page)
        cell_idx += cells_per_page
    out_path = os.path.join(OUT_DIR, f"{class_name}.pdf")
    pages[0].save(out_path, save_all=True, append_images=pages[1:], resolution=DPI)
    return out_path, cells_per_page * pages_per_class


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages-per-class", type=int, default=6,
                     help="6 pages x 42 cells/page = ~252 samples per class")
    ap.add_argument("--classes", nargs="*", default=None,
                     help="subset of folder names to generate (default: all 23)")
    args = ap.parse_args()

    targets = ALL_CLASSES
    if args.classes:
        targets = [c for c in ALL_CLASSES if c[0] in args.classes]

    print(f"{'kelas':<24}{'halaman':>10}{'total sel':>12}{'file':>10}")
    for class_name, unicode_text, label, desc in targets:
        out_path, total_cells = build_class_worksheet(class_name, unicode_text, label, desc, args.pages_per_class)
        print(f"{class_name:<24}{args.pages_per_class:>10}{total_cells:>12}  {os.path.basename(out_path)}")

    print(f"\n{len(targets)} PDF disimpan di {OUT_DIR}")


if __name__ == "__main__":
    main()
