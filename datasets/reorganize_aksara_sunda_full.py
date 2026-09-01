# -*- coding: utf-8 -*-
"""Reorganize the existing swara/ngalagena Aksara Sunda crops into the
swara_x / ngalagena_x naming scheme, and scaffold empty placeholder folders
for rarangken_x / angka_x (to be filled via the handwriting-collection
worksheets in datasets/rarangken_angka_collection/).

Source: datasets/aksara_sunda/{train,test}/<class>/*.png (30 classes, 250+15 each)
Output: datasets/aksara_sunda_full/<swara_x|ngalagena_x>/*.png (merged train+test)
        datasets/aksara_sunda_full/<rarangken_x|angka_x>/  (empty, placeholders)
"""
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "aksara_sunda")
DST = os.path.join(ROOT, "aksara_sunda_full")

SWARA_MAP = {
    "a": "swara_a", "i": "swara_i", "u": "swara_u", "e": "swara_e",
    "eu": "swara_eu", "o": "swara_o", "é": "swara_e_taling",
}
NGALAGENA = ["ba", "ca", "da", "fa", "ga", "ha", "ja", "ka", "la", "ma",
             "na", "nga", "nya", "pa", "qa", "ra", "sa", "ta", "va", "wa",
             "xa", "ya", "za"]

RARANGKEN = [
    "panghulu", "panyuku", "paneuleung", "paneleng", "panolong", "pamepet",
    "panyecek", "panglayar", "pangwisad", "pamaeh", "pamingkal",
    "panyakra", "panyiku",
]
ANGKA = [str(d) for d in range(10)]


def merge_class(src_name, dst_name):
    dst_dir = os.path.join(DST, dst_name)
    os.makedirs(dst_dir, exist_ok=True)
    n = 0
    for split in ("train", "test"):
        split_dir = os.path.join(SRC, split, src_name)
        if not os.path.isdir(split_dir):
            continue
        for fname in os.listdir(split_dir):
            src_path = os.path.join(split_dir, fname)
            dst_path = os.path.join(dst_dir, f"{split}_{fname}")
            shutil.copy2(src_path, dst_path)
            n += 1
    return n


def main():
    os.makedirs(DST, exist_ok=True)
    counts = {}

    for src_name, dst_name in SWARA_MAP.items():
        counts[dst_name] = merge_class(src_name, dst_name)

    for cons in NGALAGENA:
        dst_name = f"ngalagena_{cons}"
        counts[dst_name] = merge_class(cons, dst_name)

    for r in RARANGKEN:
        dst_name = f"rarangken_{r}"
        os.makedirs(os.path.join(DST, dst_name), exist_ok=True)
        counts[dst_name] = len(os.listdir(os.path.join(DST, dst_name)))

    for d in ANGKA:
        dst_name = f"angka_{d}"
        os.makedirs(os.path.join(DST, dst_name), exist_ok=True)
        counts[dst_name] = len(os.listdir(os.path.join(DST, dst_name)))

    print(f"{'kelas':<28}{'jumlah gambar':>15}")
    for name in sorted(counts):
        print(f"{name:<28}{counts[name]:>15}")
    total = sum(counts.values())
    print(f"\nTotal: {total} gambar di {len(counts)} kelas")
    empty = [k for k, v in counts.items() if v == 0]
    print(f"Kelas kosong (perlu dikumpulkan): {len(empty)} -> {empty}")


if __name__ == "__main__":
    main()
