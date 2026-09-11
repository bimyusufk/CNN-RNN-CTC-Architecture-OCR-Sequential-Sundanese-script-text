# -*- coding: utf-8 -*-
"""Stratified CER analysis: for every symbol POSITION in the test set's
reference labels, determine whether the model got it right (via a proper
Levenshtein alignment with traceback, not just the aggregate edit-distance
count), then bucket by that symbol's TRAINING frequency tier. This exposes
whatever the aggregate micro-averaged CER hides about rare-class failure.
"""
import csv
import json
import os
import sqlite3
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "training"))
import torch
from model import CRNN
from dataset import load_image_tensor
from utils import load_vocab, ctc_greedy_decode

SYN = os.path.join(ROOT, "datasets", "synthesis")


def compute_train_freq():
    """Symbol -> occurrence count across all active train-split sentences,
    queried live from corpus.db (not a frozen snapshot) so this stays
    correct after any future re-split/re-synthesis."""
    conn = sqlite3.connect(os.path.join(SYN, "corpus.db"))
    rows = conn.execute(
        "SELECT label FROM sentences WHERE status='active' AND split='train'"
    ).fetchall()
    conn.close()
    counter = Counter()
    for (label,) in rows:
        counter.update(label.split(" "))
    return dict(counter)


train_freq = compute_train_freq()


def tier_of(sym):
    c = train_freq.get(sym, 0)
    if c == 0:
        return "unseen_in_train"
    if c < 10:
        return "very_rare_<10"
    if c < 100:
        return "rare_10-99"
    if c < 1000:
        return "moderate_100-999"
    return "common_1000+"


def align(pred, ref):
    """Levenshtein alignment with traceback. Returns, for each ref index,
    one of 'match' or 'error' (substitution or deletion both count as the
    model failing to correctly produce that reference symbol)."""
    n, m = len(pred), len(ref)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if pred[i - 1] == ref[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)

    i, j = n, m
    ref_status = [None] * m  # index by ref position
    while i > 0 or j > 0:
        if i > 0 and j > 0 and pred[i - 1] == ref[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
            ref_status[j - 1] = "match"
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ref_status[j - 1] = "error"  # substitution
            i, j = i - 1, j - 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            ref_status[j - 1] = "error"  # deletion (ref symbol never produced)
            j -= 1
        else:
            i -= 1  # insertion in pred, doesn't correspond to a ref position
    return ref_status


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=str, default="crnn_w0.50_finalcorpus_best.pt",
                     help="filename under training/checkpoints/")
    ap.add_argument("--width", type=float, default=0.50)
    ap.add_argument("--out", type=str, default="stratified_cer_result.json",
                     help="output filename, saved under training/logs/")
    args = ap.parse_args()

    symbol_to_idx, idx_to_symbol = load_vocab(os.path.join(SYN, "vocab.json"))
    num_classes = len(symbol_to_idx) + 1
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = CRNN(num_classes, width_mult=args.width).to(device)
    ckpt = torch.load(os.path.join(ROOT, "training", "checkpoints", args.checkpoint),
                       map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    with open(os.path.join(SYN, "manifest.csv"), encoding="utf-8") as f:
        test_rows = [r for r in csv.DictReader(f) if r["split"] == "test"]

    print(f"Total test images: {len(test_rows)}", flush=True)

    tier_counts = {}  # tier -> {"match": n, "error": n}
    n_done = 0
    for r in test_rows:
        path = os.path.join(SYN, "images", r["filename"])
        if not os.path.exists(path):
            continue
        ref = r["label"].split(" ")
        tensor = load_image_tensor(path).unsqueeze(0).to(device)
        with torch.no_grad():
            log_probs = model(tensor)
            preds = log_probs.argmax(dim=2).permute(1, 0).cpu().numpy()[0].tolist()
        pred_symbols = ctc_greedy_decode(preds, idx_to_symbol, blank=0)

        ref_status = align(pred_symbols, ref)
        for sym, status in zip(ref, ref_status):
            tier = tier_of(sym)
            tier_counts.setdefault(tier, {"match": 0, "error": 0})
            tier_counts[tier][status if status else "error"] += 1

        n_done += 1
        if n_done % 200 == 0:
            print(f"  {n_done}/{len(test_rows)} diproses", flush=True)

    print()
    print("=== HASIL STRATIFIKASI (akurasi per-simbol berdasar tingkat kelangkaan di TRAIN) ===")
    order = ["unseen_in_train", "very_rare_<10", "rare_10-99", "moderate_100-999", "common_1000+"]
    results = {}
    for tier in order:
        c = tier_counts.get(tier, {"match": 0, "error": 0})
        total = c["match"] + c["error"]
        acc = c["match"] / total if total else None
        results[tier] = {"match": c["match"], "error": c["error"], "total": total,
                          "accuracy": acc}
        acc_str = f"{acc*100:.1f}%" if acc is not None else "N/A (tidak ada di test)"
        print(f"{tier:22s}: n={total:6d}  benar={c['match']:6d}  salah={c['error']:6d}  akurasi={acc_str}")

    out_path = os.path.join(ROOT, "training", "logs", args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\nDisimpan ke: {out_path}")


if __name__ == "__main__":
    main()
