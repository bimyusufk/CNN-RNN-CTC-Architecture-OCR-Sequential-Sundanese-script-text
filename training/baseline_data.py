# -*- coding: utf-8 -*-
"""Generate the trivial-segmentation baseline's data: isolated syllable
crops, one classification example per (image, grapheme-class) pair --
NOT sequences. This is legitimate specifically because our synthetic
sentence images have exactly-known syllable positions by construction (see
proposal Bab III), so "segmentation" is free -- a real photographed
document would need an actual detector.

  - Train: 15 renders per TRAIN-vocab symbol (349 classes), drawn from the
    TRAIN crop pool -- balanced across classes (real sentence frequency is
    heavily skewed, e.g. pamaeh-bearing syllables vs. rare panyiku ones;
    balancing here avoids the classifier just learning the frequency prior).
  - Val/Test: the SAME val/test sentences used for the CRNN, decomposed
    into their true syllables (drawn from the EVAL crop pool) -- so the
    baseline's sentence-level CER is directly comparable to the CRNN's.

Usage: python baseline_data.py
"""
import csv
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "datasets", "rarangken_angka_collection"))

from compositor import make_syllable_generic, segment_syllables
from demo_sentence import crop_pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYN_DIR = os.path.join(ROOT, "datasets", "synthesis")
CORPUS_PKL = os.path.join(ROOT, "datasets", "nusaaksara_corpus", "filtered_sunda.pkl")
OUT_DIR = os.path.join(ROOT, "training", "baseline_data")
IMAGES_DIR = os.path.join(OUT_DIR, "images")

RENDERS_PER_TRAIN_CLASS = 15


def label_to_codepoints(label):
    """A vocab label IS the raw Unicode substring for that syllable (see
    compositor.syllable_label) -- decode it straight back to (base_cp,
    mark_cps) instead of keeping a separate mapping table."""
    cps = [ord(c) for c in label]
    return cps[0], cps[1:]


def main():
    with open(os.path.join(SYN_DIR, "crop_split.json"), encoding="utf-8") as f:
        crop_split = json.load(f)
    with open(os.path.join(SYN_DIR, "sentence_split.json"), encoding="utf-8") as f:
        sent_split = json.load(f)
    with open(os.path.join(SYN_DIR, "vocab.json"), encoding="utf-8") as f:
        vocab = json.load(f)
    with open(CORPUS_PKL, "rb") as f:
        corpus = pickle.load(f)
    passed = corpus["passed"]

    pool_train = {cls: p["train"] for cls, p in crop_split.items()}
    pool_eval = {cls: p["eval"] for cls, p in crop_split.items()}

    for split in ("train", "val", "test"):
        os.makedirs(os.path.join(IMAGES_DIR, split), exist_ok=True)

    manifest_rows = []

    # "<sp>" is a CTC vocabulary symbol (word-space) but not an image class --
    # there's no syllable to render for it. The trivial baseline gets word
    # boundaries for free (same premise as character positions being known
    # by construction), so it's reinserted structurally at eval time rather
    # than classified.
    syllable_vocab = [s for s in vocab if s != "<sp>"]

    # --- train: balanced, one render per (class, k) ---
    print(f"Membuat data latih baseline: {len(syllable_vocab)} kelas x {RENDERS_PER_TRAIN_CLASS} render")
    for label in syllable_vocab:
        base_cp, mark_cps = label_to_codepoints(label)
        for k in range(RENDERS_PER_TRAIN_CLASS):
            with crop_pool(pool_train):
                img = make_syllable_generic(base_cp, mark_cps)
            fname = f"{abs(hash(label)) % 100000}_{k:02d}.png"
            img.save(os.path.join(IMAGES_DIR, "train", fname))
            manifest_rows.append({"filename": f"train/{fname}", "split": "train", "label": label})

    # --- val/test: decompose the actual held-out sentences ---
    # word_idx is tracked (not just flat position) so "<sp>" -- a real CTC
    # vocabulary symbol the CRNN must predict -- can be reinserted at eval
    # time between word groups. Word boundaries are known for free here
    # (same premise as character positions), so the baseline never has to
    # classify them.
    for split in ("val", "test"):
        print(f"Membuat data {split} baseline dari kalimat asli...")
        for sent_idx in sent_split[split]:
            row_idx, text, n_syll = passed[sent_idx]
            word_idx = 0
            started_word = False
            items = []  # (base_cp, mark_cps, word_idx)
            for base_cp, marks in segment_syllables(text):
                if base_cp is None:
                    if started_word:
                        word_idx += 1
                        started_word = False
                    continue
                items.append((base_cp, marks, word_idx))
                started_word = True

            pos = 0
            for base_cp, mark_cps, w_idx in items:
                with crop_pool(pool_eval):
                    img = make_syllable_generic(base_cp, mark_cps)
                label = chr(base_cp) + "".join(chr(m) for m in mark_cps)
                fname = f"{split}_{row_idx:04d}_{pos:02d}.png"
                img.save(os.path.join(IMAGES_DIR, split, fname))
                manifest_rows.append({
                    "filename": f"{split}/{fname}", "split": split, "label": label,
                    "sentence_row_idx": row_idx, "position": pos, "word_idx": w_idx,
                    "n_syll_in_sentence": len(items),
                })
                pos += 1

    manifest_path = os.path.join(OUT_DIR, "manifest.csv")
    fieldnames = ["filename", "split", "label", "sentence_row_idx", "position", "word_idx", "n_syll_in_sentence"]
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in manifest_rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"\nTotal: {len(manifest_rows)} citra")
    for s in ("train", "val", "test"):
        print(f"  {s}: {sum(1 for r in manifest_rows if r['split']==s)}")
    print(f"Disimpan ke: {OUT_DIR}")


if __name__ == "__main__":
    main()
