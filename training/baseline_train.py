# -*- coding: utf-8 -*-
"""Train the trivial-segmentation baseline classifier (plain isolated-
syllable classification, no CTC) and evaluate it at the SENTENCE level
(reinsert "<sp>" at known word boundaries, compare to the same ground
truth the CRNN is scored against) so its CER/WER is directly comparable to
train_crnn.py's numbers.

Usage: python baseline_train.py --epochs 40
"""
import argparse
import csv
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import Dataset, DataLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import TrivialBaselineCNN
from utils import cer, wer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.join(ROOT, "training", "baseline_data")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
MANIFEST_PATH = os.path.join(BASE_DIR, "manifest.csv")
SYN_MANIFEST_PATH = os.path.join(ROOT, "datasets", "synthesis", "manifest.csv")
CKPT_PATH = os.path.join(ROOT, "training", "checkpoints", "baseline_best.pt")
LOG_PATH = os.path.join(ROOT, "training", "logs", "baseline.json")

IMG_SIZE = 64


def load_image(path):
    img = Image.open(path).convert("L").resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


class SyllableDataset(Dataset):
    def __init__(self, rows, class_to_idx):
        self.rows = rows
        self.class_to_idx = class_to_idx

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        img = load_image(os.path.join(IMAGES_DIR, r["filename"]))
        label = self.class_to_idx[r["label"]]
        return img, label


def load_true_sentence_labels():
    """{(split, row_idx): [true symbols incl. <sp>]} from the CRNN's own
    manifest, so both models are scored against identical ground truth."""
    out = {}
    with open(SYN_MANIFEST_PATH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["split"], int(r["row_idx"]))
            if key not in out:
                out[key] = r["label"].split(" ") if r["label"] else []
    return out


def evaluate_sentences(model, rows, class_to_idx, idx_to_class, device, split, true_labels):
    """Group baseline rows by (split, sentence_row_idx), classify each
    syllable crop, reinsert <sp> at word_idx boundaries (known for free),
    compare to true_labels."""
    model.eval()
    by_sentence = {}
    for r in rows:
        key = int(r["sentence_row_idx"])
        by_sentence.setdefault(key, []).append(r)

    total_cer, total_wer, exact, n = 0.0, 0.0, 0, 0
    with torch.no_grad():
        for row_idx, syll_rows in by_sentence.items():
            syll_rows.sort(key=lambda r: int(r["position"]))
            imgs = torch.stack([load_image(os.path.join(IMAGES_DIR, r["filename"])) for r in syll_rows]).to(device)
            logits = model(imgs)
            preds = logits.argmax(dim=1).cpu().tolist()

            pred_symbols = []
            prev_word = None
            for r, p in zip(syll_rows, preds):
                w = int(r["word_idx"])
                if prev_word is not None and w != prev_word:
                    pred_symbols.append("<sp>")
                pred_symbols.append(idx_to_class[p])
                prev_word = w

            true_symbols = true_labels.get((split, row_idx), [])
            total_cer += cer(pred_symbols, true_symbols)
            total_wer += wer(pred_symbols, true_symbols)
            exact += int(pred_symbols == true_symbols)
            n += 1
    model.train()
    if n == 0:
        return {"cer": 1.0, "wer": 1.0, "exact_match": 0.0, "n": 0}
    return {"cer": total_cer / n, "wer": total_wer / n, "exact_match": exact / n, "n": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=10)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(CKPT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    train_rows = [r for r in all_rows if r["split"] == "train"]
    val_rows = [r for r in all_rows if r["split"] == "val"]
    test_rows = [r for r in all_rows if r["split"] == "test"]

    classes = sorted(set(r["label"] for r in train_rows))
    class_to_idx = {c: i for i, c in enumerate(classes)}
    idx_to_class = {i: c for i, c in enumerate(classes)}
    print(f"Baseline: {len(classes)} kelas suku kata, {len(train_rows)} train / {len(val_rows)} val / {len(test_rows)} test citra")

    train_ds = SyllableDataset(train_rows, class_to_idx)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)

    true_labels = load_true_sentence_labels()

    model = TrivialBaselineCNN(len(classes)).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Baseline parameter: {n_params:,}  device: {device}")

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    history = []
    best_val_cer = float("inf")
    epochs_no_improve = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss, n_correct, n_total = 0.0, 0, 0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(device), labels.to(device)
            logits = model(imgs)
            loss = criterion(logits, labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_correct += (logits.argmax(1) == labels).sum().item()
            n_total += labels.size(0)

        val_metrics = evaluate_sentences(model, val_rows, class_to_idx, idx_to_class, device, "val", true_labels)
        print(f"[baseline] epoch {epoch}/{args.epochs}  train_loss={epoch_loss/len(train_loader):.4f}  "
              f"train_acc={n_correct/n_total:.4f}  val_cer={val_metrics['cer']:.4f}  "
              f"val_wer={val_metrics['wer']:.4f}  val_exact={val_metrics['exact_match']:.4f}")

        history.append({"epoch": epoch, "train_loss": epoch_loss/len(train_loader),
                         "train_acc": n_correct/n_total, **val_metrics})
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump({"n_params": n_params, "n_classes": len(classes), "history": history}, f, indent=1)

        if val_metrics["cer"] < best_val_cer:
            best_val_cer = val_metrics["cer"]
            epochs_no_improve = 0
            torch.save({"model_state": model.state_dict(), "classes": classes,
                        "epoch": epoch, "val_cer": best_val_cer}, CKPT_PATH)
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= args.patience:
                print(f"[baseline] early stop di epoch {epoch}")
                break

    # final test evaluation using the best checkpoint
    ckpt = torch.load(CKPT_PATH, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    test_metrics = evaluate_sentences(model, test_rows, class_to_idx, idx_to_class, device, "test", true_labels)
    print(f"[baseline] TEST: cer={test_metrics['cer']:.4f} wer={test_metrics['wer']:.4f} "
          f"exact={test_metrics['exact_match']:.4f} (n={test_metrics['n']})")

    with open(os.path.join(ROOT, "training", "logs", "baseline_test.json"), "w", encoding="utf-8") as f:
        json.dump(test_metrics, f, indent=1)


if __name__ == "__main__":
    main()
