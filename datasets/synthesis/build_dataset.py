# -*- coding: utf-8 -*-
"""Full synthesis pipeline: NusaAksara's 801 filtered Sunda sentences ->
a labeled image dataset for CRNN+CTC training, with a genuine two-layer
train/val/test split (unseen SENTENCES *and* unseen physical CROP
INSTANCES in val/test -- not just one or the other).

Split design (see project discussion, 2026-08-29):
  - Sentence-level population is small (801) -- 80/10/10 keeps val/test at
    a large enough absolute count (~80 each) for stable CER/WER, rather
    than a naive "big data" ratio like 99/1 which would leave ~8 test
    sentences.
  - Crop-instance-level population is larger (hundreds per class) -- 80/20
    is enough there; the same 20% "eval pool" is shared by val and test
    (neither leaks into train, val/test don't need to be mutually
    exclusive from each other).
  - Training volume comes from the render multiplier (many renders per
    train sentence, each drawing different random crop instances from the
    train pool), not from inflating the sentence-level split.

Usage:
    python datasets/synthesis/build_dataset.py --smoke-test   # tiny run first
    python datasets/synthesis/build_dataset.py                # full run
"""
import argparse
import csv
import json
import os
import pickle
import random

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "rarangken_angka_collection"))

from compositor import render_text, segment_syllables
from demo_sentence import crop_pool, DATASET_DIR

ROOT = os.path.dirname(os.path.abspath(__file__))
CORPUS_PKL = os.path.join(os.path.dirname(ROOT), "nusaaksara_corpus", "filtered_sunda.pkl")
IMAGES_DIR = os.path.join(ROOT, "images")
SPLIT_SEED = 42

RENDERS_PER_TRAIN = 8
RENDERS_PER_EVAL = 3  # applies to both val and test
CROP_TRAIN_FRAC = 0.8
SENT_TRAIN_FRAC = 0.8
SENT_VAL_FRAC = 0.1  # remainder goes to test


def build_crop_split():
    """{class_name: {"train": [files], "eval": [files]}} for every class
    except angka_* (still deferred)."""
    rng = random.Random(SPLIT_SEED)
    split = {}
    for cls in sorted(os.listdir(DATASET_DIR)):
        d = os.path.join(DATASET_DIR, cls)
        if not os.path.isdir(d) or cls.startswith("angka_"):
            continue
        files = sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))
        rng.shuffle(files)
        n_train = int(len(files) * CROP_TRAIN_FRAC)
        split[cls] = {"train": files[:n_train], "eval": files[n_train:]}
        if len(files[n_train:]) == 0:
            raise ValueError(f"Kelas {cls} tidak punya sisa untuk pool eval (hanya {len(files)} gambar).")
    return split


def build_sentence_split(n_sentences):
    rng = random.Random(SPLIT_SEED + 1)
    idxs = list(range(n_sentences))
    rng.shuffle(idxs)
    n_train = int(n_sentences * SENT_TRAIN_FRAC)
    n_val = int(n_sentences * SENT_VAL_FRAC)
    return {
        "train": sorted(idxs[:n_train]),
        "val": sorted(idxs[n_train:n_train + n_val]),
        "test": sorted(idxs[n_train + n_val:]),
    }


def crop_pool_for(split_name, crop_split):
    key = "train" if split_name == "train" else "eval"
    return {cls: pools[key] for cls, pools in crop_split.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke-test", action="store_true",
                     help="tiny run: 3 train/2 val/2 test sentences, few renders each")
    args = ap.parse_args()

    with open(CORPUS_PKL, "rb") as f:
        corpus = pickle.load(f)
    passed = corpus["passed"]  # list of (row_idx, transcription_text, n_syll)
    print(f"Korpus: {len(passed)} kalimat lolos filter")

    crop_split = build_crop_split()
    sent_split = build_sentence_split(len(passed))

    if args.smoke_test:
        sent_split = {
            "train": sent_split["train"][:3],
            "val": sent_split["val"][:2],
            "test": sent_split["test"][:2],
        }
        renders = {"train": 2, "val": 1, "test": 1}
        print("MODE SMOKE-TEST:", {k: len(v) for k, v in sent_split.items()})
    else:
        renders = {"train": RENDERS_PER_TRAIN, "val": RENDERS_PER_EVAL, "test": RENDERS_PER_EVAL}
        print("Split kalimat:", {k: len(v) for k, v in sent_split.items()})

    with open(os.path.join(ROOT, "crop_split.json"), "w", encoding="utf-8") as f:
        json.dump(crop_split, f)
    with open(os.path.join(ROOT, "sentence_split.json"), "w", encoding="utf-8") as f:
        json.dump(sent_split, f)

    manifest_rows = []
    vocab = set()
    failures = []

    for split_name in ("train", "val", "test"):
        out_dir = os.path.join(IMAGES_DIR, split_name)
        os.makedirs(out_dir, exist_ok=True)
        pool = crop_pool_for(split_name, crop_split)
        n_renders = renders[split_name]

        for sent_idx in sent_split[split_name]:
            row_idx, text, n_syll = passed[sent_idx]
            for r in range(n_renders):
                with crop_pool(pool):
                    img, labels = render_text(text)
                if img is None:
                    failures.append((split_name, row_idx, "empty render"))
                    continue
                fname = f"{split_name}_{row_idx:04d}_{r:02d}.png"
                img.save(os.path.join(out_dir, fname))
                label_str = " ".join(labels)
                if split_name == "train":
                    vocab.update(labels)
                manifest_rows.append({
                    "filename": f"{split_name}/{fname}",
                    "split": split_name,
                    "row_idx": row_idx,
                    "label": label_str,
                    "n_symbols": len(labels),
                })

    manifest_path = os.path.join(ROOT, "manifest.csv")
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "split", "row_idx", "label", "n_symbols"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    vocab_list = sorted(vocab)
    with open(os.path.join(ROOT, "vocab.json"), "w", encoding="utf-8") as f:
        json.dump(vocab_list, f, ensure_ascii=False, indent=1)

    print(f"\nTotal citra dihasilkan: {len(manifest_rows)}")
    for s in ("train", "val", "test"):
        n = sum(1 for r in manifest_rows if r["split"] == s)
        print(f"  {s}: {n}")
    print(f"Ukuran vocabulary CTC (dari train saja): {len(vocab_list)}")
    if failures:
        print(f"Gagal render: {len(failures)} -> {failures[:5]}")
    print(f"\nDisimpan ke: {ROOT}")


if __name__ == "__main__":
    main()
