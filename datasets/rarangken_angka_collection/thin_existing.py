# -*- coding: utf-8 -*-
"""One-off fix: the collected rarangken_* strokes read too thick (brush was
calibrated for legibility, not for matching the finer default stroke weight
elsewhere in the dataset). Thins every rarangken_* image to ~60% of its
current stroke width, in place. Backs up the untouched inputs first.

Usage: python datasets/rarangken_angka_collection/thin_existing.py
"""
import os
import shutil

from PIL import Image

from image_utils import thin_stroke, estimate_stroke_width
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(os.path.dirname(ROOT), "aksara_sunda_full")
BACKUP_DIR = os.path.join(ROOT, "_backup_before_thinning")
TARGET_FACTOR = 0.6


def stroke_width(img_L):
    arr = np.array(img_L)
    ink = (arr < 128).astype(np.uint8) * 255
    return estimate_stroke_width(ink)


def main():
    target_dirs = [d for d in os.listdir(DATASET_DIR) if d.startswith("rarangken_")]

    total, fixed = 0, 0
    before_w, after_w = [], []

    for class_name in sorted(target_dirs):
        class_dir = os.path.join(DATASET_DIR, class_name)
        files = [f for f in os.listdir(class_dir) if f.lower().endswith(".png")]
        if not files:
            continue

        backup_class_dir = os.path.join(BACKUP_DIR, class_name)
        os.makedirs(backup_class_dir, exist_ok=True)

        for fname in files:
            path = os.path.join(class_dir, fname)
            backup_path = os.path.join(backup_class_dir, fname)
            if not os.path.exists(backup_path):
                shutil.copy2(path, backup_path)

            im = Image.open(path).convert("L")
            total += 1
            w0 = stroke_width(im)
            if w0 <= 0:
                continue
            before_w.append(w0)

            thinned = thin_stroke(im, target_factor=TARGET_FACTOR)
            thinned.save(path)
            fixed += 1
            after_w.append(stroke_width(thinned))

    def stats(xs):
        if not xs:
            return "n/a"
        xs = sorted(xs)
        return f"median={xs[len(xs)//2]:.1f}px mean={sum(xs)/len(xs):.1f}px min={xs[0]:.1f}px max={xs[-1]:.1f}px"

    print(f"Diproses: {total} gambar, {fixed} ditipiskan")
    print(f"Ketebalan SEBELUM: {stats(before_w)}")
    print(f"Ketebalan SESUDAH: {stats(after_w)}")
    print(f"Backup asli tersimpan di: {BACKUP_DIR}")


if __name__ == "__main__":
    main()
