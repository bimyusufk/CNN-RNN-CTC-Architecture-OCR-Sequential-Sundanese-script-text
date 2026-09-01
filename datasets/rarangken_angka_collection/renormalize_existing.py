# -*- coding: utf-8 -*-
"""One-off fix for samples collected before image_utils.crop_to_content
existed: re-crop every already-collected rarangken_*/angka_* image tight to
its ink (with padding), in place. Backs up the untouched originals first.

Usage: python datasets/rarangken_angka_collection/renormalize_existing.py
"""
import os
import shutil

from PIL import Image

from image_utils import finalize_224

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(os.path.dirname(ROOT), "aksara_sunda_full")
BACKUP_DIR = os.path.join(ROOT, "_backup_before_renormalize")


def fill_ratio(img_L):
    bbox = img_L.point(lambda p: 255 - p).getbbox()
    if bbox is None:
        return 0.0
    w, h = img_L.size
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return max(bw / w, bh / h)


def main():
    target_dirs = [d for d in os.listdir(DATASET_DIR)
                   if d.startswith("rarangken_") or d.startswith("angka_")]

    total, fixed, blank_skipped = 0, 0, 0
    before_fills, after_fills = [], []

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
            before_fills.append(fill_ratio(im))
            total += 1

            fixed_im = finalize_224(im)
            if fixed_im is None:
                blank_skipped += 1
                continue
            fixed_im.save(path)
            after_fills.append(fill_ratio(fixed_im))
            fixed += 1

    def stats(xs):
        if not xs:
            return "n/a"
        xs = sorted(xs)
        return f"median={xs[len(xs)//2]*100:.0f}% mean={sum(xs)/len(xs)*100:.0f}% min={xs[0]*100:.0f}% max={xs[-1]*100:.0f}%"

    print(f"Diproses: {total} gambar, {fixed} diperbaiki, {blank_skipped} kosong/dilewati")
    print(f"Fill ratio SEBELUM: {stats(before_fills)}")
    print(f"Fill ratio SESUDAH: {stats(after_fills)}")
    print(f"Backup asli tersimpan di: {BACKUP_DIR}")


if __name__ == "__main__":
    main()
