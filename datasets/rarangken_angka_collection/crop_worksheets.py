# -*- coding: utf-8 -*-
"""Turn scanned/photographed filled-in worksheets back into individual
224x224 class images, matching the format of datasets/aksara_sunda_full/.

Usage:
    1. Fill in worksheets/<class_name>.pdf by hand (pen, black ink).
    2. Scan or photograph each filled page as flat/rectangular as possible
       and save into scans/<class_name>/*.jpg (or .png), one file per page,
       any filename -- order does not matter.
    3. Run: python datasets/rarangken_angka_collection/crop_worksheets.py

The script finds the four solid black corner registration squares printed
by generate_worksheets.py, perspective-corrects the page to the exact
generator geometry, then slices the known 6x7 cell grid -- this is the same
"trivial segmentation" trick used in the skripsi's synthetic-data pipeline:
cropping is exact because cell positions are known by construction, not
detected from ink.

Output: datasets/aksara_sunda_full/<class_name>/scan_<file>_<cell_idx>.png
"""
import glob
import os

import cv2
import numpy as np
from PIL import Image

from image_utils import finalize_224

ROOT = os.path.dirname(os.path.abspath(__file__))
SCAN_DIR = os.path.join(ROOT, "scans")
DATASET_DIR = os.path.join(os.path.dirname(ROOT), "aksara_sunda_full")

DPI = 300
PAGE_W, PAGE_H = int(8.27 * DPI), int(11.69 * DPI)
MARGIN = 150
COLS, ROWS = 6, 7
REG_SIZE = 70
GRID_TOP = 340
GRID_BOTTOM = PAGE_H - MARGIN
GRID_LEFT = MARGIN
GRID_RIGHT = PAGE_W - MARGIN

OUT_SIZE = 224


def find_registration_squares(gray):
    """Find 4 solid black squares near the page corners via contour search."""
    h, w = gray.shape
    _, thresh = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < (w * h) * 0.00005 or area > (w * h) * 0.01:
            continue
        x, y, cw, ch = cv2.boundingRect(c)
        aspect = cw / max(ch, 1)
        if 0.6 < aspect < 1.6:
            (mx, my), _, _ = cv2.minAreaRect(c)
            candidates.append((mx, my, area))

    if len(candidates) < 4:
        return None

    quadrants = {"tl": None, "tr": None, "bl": None, "br": None}
    cx_mid, cy_mid = w / 2, h / 2
    for x, y, area in candidates:
        key = ("t" if y < cy_mid else "b") + ("l" if x < cx_mid else "r")
        if quadrants[key] is None or area > quadrants[key][2]:
            quadrants[key] = (x, y, area)

    if any(v is None for v in quadrants.values()):
        return None
    return {k: (v[0], v[1]) for k, v in quadrants.items()}


A4_RATIO = PAGE_H / PAGE_W


def looks_already_rectified(img, tol=0.03):
    """True if the image's aspect ratio already matches A4 -- i.e. it came
    from a phone scanning app (Adobe Scan / Google Drive scan / CamScanner /
    a flatbed scanner) that already cropped+rectified the page. In that case
    skip perspective correction entirely and just resize, which is far more
    reliable than re-detecting registration squares on an already-clean scan.
    """
    h, w = img.shape[:2]
    ratio = h / w
    return abs(ratio - A4_RATIO) / A4_RATIO < tol or abs((1 / ratio) - A4_RATIO) / A4_RATIO < tol


def perspective_correct(img):
    if looks_already_rectified(img):
        h, w = img.shape[:2]
        if w > h:  # landscape scan of a portrait page -> rotate
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        return cv2.resize(img, (PAGE_W, PAGE_H), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    pts = find_registration_squares(gray)
    if pts is None:
        return None

    src = np.float32([pts["tl"], pts["tr"], pts["bl"], pts["br"]])
    dst = np.float32([
        [GRID_LEFT, GRID_TOP], [GRID_RIGHT, GRID_TOP],
        [GRID_LEFT, GRID_BOTTOM], [GRID_RIGHT, GRID_BOTTOM],
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (PAGE_W, PAGE_H), borderValue=(255, 255, 255))
    return warped


INK_THRESHOLD = 130  # fixed, not Otsu-adaptive: pen ink scans near-black
                      # (~0-80); must stay well below the light-gray QC index
                      # labels (#bbbbbb=187) and cell borders (#999999=153)
                      # printed on each cell, or those get picked up as
                      # "ink" by an adaptive threshold on a blank cell.


def clean_binarize(cell_bgr):
    gray = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(gray, INK_THRESHOLD, 255, cv2.THRESH_BINARY)
    return bw  # single-channel, not yet cropped/resized


def crop_cells(warped):
    """Slice the grid, then crop each cell tight to its ink (with padding)
    before resizing -- otherwise a small mark drawn in the middle of a
    generously-sized worksheet cell ends up with a large dead-space margin,
    which throws off later word-synthesis compositing."""
    cell_w = (GRID_RIGHT - GRID_LEFT) / COLS
    cell_h = (GRID_BOTTOM - GRID_TOP) / ROWS
    # must clear REG_SIZE/2 (registration squares sit AT the 4 grid corners,
    # so the corner cells' crop region needs enough margin not to catch a
    # sliver of one) with room to spare.
    pad = max(45, REG_SIZE)
    cells = []
    for row in range(ROWS):
        for col in range(COLS):
            x0 = int(GRID_LEFT + col * cell_w + pad)
            y0 = int(GRID_TOP + row * cell_h + pad)
            x1 = int(GRID_LEFT + (col + 1) * cell_w - pad)
            y1 = int(GRID_TOP + (row + 1) * cell_h - pad)
            cell = warped[y0:y1, x0:x1]
            bw = clean_binarize(cell)
            # Reject on RAW ink density before crop-to-content -- otherwise a
            # tiny JPEG/compression noise speck in a truly blank cell gets
            # blown up to ~59% fill by the padding step below and reads as
            # "real" content once normalized.
            if np.mean(bw < 128) < 0.003:
                cells.append(None)
                continue
            pil_l = Image.fromarray(bw)
            finalized = finalize_224(pil_l, out_size=OUT_SIZE)
            if finalized is None:
                cells.append(None)
            else:
                cells.append(cv2.cvtColor(np.array(finalized), cv2.COLOR_GRAY2BGR))
    return cells


def cell_is_blank(cell_bgr, ink_frac_threshold=0.002):
    gray = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY)
    ink = np.mean(gray < 128)
    return ink < ink_frac_threshold


def process_class(class_name):
    src_dir = os.path.join(SCAN_DIR, class_name)
    if not os.path.isdir(src_dir):
        return 0, 0
    out_dir = os.path.join(DATASET_DIR, class_name)
    os.makedirs(out_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(src_dir, "*.jpg")) +
                    glob.glob(os.path.join(src_dir, "*.jpeg")) +
                    glob.glob(os.path.join(src_dir, "*.png")))
    saved, skipped_blank, failed = 0, 0, 0
    for fpath in files:
        img = cv2.imread(fpath)
        if img is None:
            failed += 1
            continue
        warped = perspective_correct(img)
        if warped is None:
            print(f"  [!] registrasi gagal, dilewati: {fpath}")
            failed += 1
            continue
        cells = crop_cells(warped)
        base = os.path.splitext(os.path.basename(fpath))[0]
        for i, cell in enumerate(cells, start=1):
            if cell is None or cell_is_blank(cell):
                skipped_blank += 1
                continue
            out_path = os.path.join(out_dir, f"scan_{base}_{i:03d}.png")
            cv2.imwrite(out_path, cell)
            saved += 1
    if failed:
        print(f"  {failed} halaman gagal diproses (cek scan/foto: harus terlihat 4 kotak hitam di sudut)")
    return saved, skipped_blank


def main():
    if not os.path.isdir(SCAN_DIR):
        print(f"Folder scan belum ada: {SCAN_DIR}")
        print("Buat folder scans/<nama_kelas>/ lalu taruh hasil scan/foto di dalamnya.")
        return

    class_dirs = sorted(d for d in os.listdir(SCAN_DIR) if os.path.isdir(os.path.join(SCAN_DIR, d)))
    if not class_dirs:
        print(f"Tidak ada folder kelas di {SCAN_DIR} -- belum ada yang discan.")
        return

    print(f"{'kelas':<24}{'tersimpan':>12}{'kosong':>10}")
    total_saved = 0
    for class_name in class_dirs:
        saved, blank = process_class(class_name)
        total_saved += saved
        print(f"{class_name:<24}{saved:>12}{blank:>10}")
    print(f"\nTotal {total_saved} gambar baru ditambahkan ke {DATASET_DIR}")


if __name__ == "__main__":
    main()
