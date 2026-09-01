# -*- coding: utf-8 -*-
"""Train the CRNN+CTC model at a given width multiplier on the NusaAksara
synthetic corpus. Deployed/evaluated architecture is ALWAYS plain CRNN+CTC
(model.CRNN.forward) -- the proposal's core architecture is preserved
exactly. Two training-time-only improvements, both discarded at inference:

  1. LR schedule: linear warmup + cosine decay (matches PP-OCRv6's training
     recipe -- our first run used a flat LR, which the overnight results
     showed converges to near-zero train loss by epoch ~15-20 then
     oscillates noisily for the rest of the budget).
  2. Auxiliary decoder (--use-aux, default on): a small Transformer decoder
     reads the SAME shared CNN+BiLSTM feature sequence as the CTC head and
     is trained to predict the target sequence autoregressively
     (cross-entropy, label smoothing) -- an implicit language-model
     regularizer on the shared representation, same role as NRTR in
     PP-OCRv6 or the attention branch in GTC (Hu et al. 2020). Only the
     CTC head is used for evaluation, checkpointing, and inference; the aux
     decoder's own weights are not required to run the saved model.

Usage: python train_crnn.py --width 0.50 --epochs 60
       python train_crnn.py --width 0.50 --epochs 60 --no-aux   (ablation)
"""
import argparse
import json
import math
import os
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from dataset import CRNNDataset, load_manifest, TrainCollate, eval_collate
from model import CRNN, AuxDecoder, LSTM_HIDDEN, AUX_PAD, AUX_SPECIAL_TOKENS
from utils import load_vocab, cer, wer, ctc_greedy_decode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYN_DIR = os.path.join(ROOT, "datasets", "synthesis")
IMAGES_DIR = os.path.join(SYN_DIR, "images")
MANIFEST_PATH = os.path.join(SYN_DIR, "manifest.csv")
VOCAB_PATH = os.path.join(SYN_DIR, "vocab.json")
CKPT_DIR = os.path.join(ROOT, "training", "checkpoints")
LOG_DIR = os.path.join(ROOT, "training", "logs")


def evaluate(model, loader, idx_to_symbol, device, max_batches=None):
    """Uses ONLY model.forward() (the CTC path) -- identical to how the
    final deployed model would run, whether or not the aux decoder was
    used during training."""
    model.eval()
    total_cer, total_wer, n = 0.0, 0.0, 0
    exact = 0
    with torch.no_grad():
        for bi, (images, input_lengths, labels_list, _) in enumerate(loader):
            if max_batches and bi >= max_batches:
                break
            images = images.to(device)
            log_probs = model(images)  # (T, B, C)
            preds = log_probs.argmax(dim=2).permute(1, 0).cpu().numpy()  # (B, T)
            for b in range(len(labels_list)):
                T = input_lengths[b].item()
                pred_ids = preds[b, :T].tolist()
                pred_symbols = ctc_greedy_decode(pred_ids, idx_to_symbol, blank=0)
                true_symbols = labels_list[b]
                total_cer += cer(pred_symbols, true_symbols)
                total_wer += wer(pred_symbols, true_symbols)
                exact += int(pred_symbols == true_symbols)
                n += 1
    model.train()
    if n == 0:
        return {"cer": 1.0, "wer": 1.0, "exact_match": 0.0, "n": 0}
    return {"cer": total_cer / n, "wer": total_wer / n, "exact_match": exact / n, "n": n}


def make_lr_lambda(warmup_epochs, total_epochs):
    def lr_lambda(epoch):
        if epoch < warmup_epochs:
            return (epoch + 1) / max(1, warmup_epochs)
        progress = (epoch - warmup_epochs) / max(1, total_epochs - warmup_epochs)
        progress = min(1.0, progress)
        return 0.5 * (1.0 + math.cos(math.pi * progress))
    return lr_lambda


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=float, required=True, choices=[0.25, 0.50, 0.75, 1.00, 1.50])
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--warmup-epochs", type=int, default=5)
    ap.add_argument("--patience", type=int, default=20, help="early stop if val CER doesn't improve for N epochs")
    ap.add_argument("--use-aux", dest="use_aux", action="store_true", default=True)
    ap.add_argument("--no-aux", dest="use_aux", action="store_false")
    ap.add_argument("--aux-weight", type=float, default=1.0)
    ap.add_argument("--augment", dest="augment", action="store_true", default=True,
                     help="on-the-fly rotation/scale/elastic augmentation, train split only")
    ap.add_argument("--no-augment", dest="augment", action="store_false")
    ap.add_argument("--tag-suffix", type=str, default="")
    args = ap.parse_args()

    os.makedirs(CKPT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    symbol_to_idx, idx_to_symbol = load_vocab(VOCAB_PATH)
    num_classes = len(symbol_to_idx) + 1  # +1 for CTC blank at index 0
    aux_vocab_size = len(symbol_to_idx) + AUX_SPECIAL_TOKENS  # PAD/BOS/EOS + real symbols

    manifest = load_manifest(MANIFEST_PATH)
    train_ds = CRNNDataset(manifest, IMAGES_DIR, "train", augment=args.augment)
    val_ds = CRNNDataset(manifest, IMAGES_DIR, "val")
    test_ds = CRNNDataset(manifest, IMAGES_DIR, "test")

    # Augmentation is CPU-bound (~0.12s/sample even after optimization,
    # dominated by scipy's per-pixel remapping on wide sentence images) --
    # with num_workers=0 that would add ~10min/epoch serialized against the
    # GPU. Parallelize across worker processes so it overlaps with GPU
    # compute instead of blocking it.
    train_workers = min(8, os.cpu_count() or 0) if args.augment else 0
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                               collate_fn=TrainCollate(symbol_to_idx),
                               num_workers=train_workers,
                               persistent_workers=(train_workers > 0))
    val_loader = DataLoader(val_ds, batch_size=1, shuffle=False, collate_fn=eval_collate, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=1, shuffle=False, collate_fn=eval_collate, num_workers=0)

    model = CRNN(num_classes, width_mult=args.width).to(device)
    n_params = model.count_params()

    aux_decoder = None
    aux_params = 0
    if args.use_aux:
        aux_decoder = AuxDecoder(memory_dim=LSTM_HIDDEN * 2, aux_vocab_size=aux_vocab_size).to(device)
        aux_params = sum(p.numel() for p in aux_decoder.parameters())
    print(f"[width={args.width}] parameter CRNN: {n_params:,}"
          + (f"  + AuxDecoder (training-only): {aux_params:,}" if aux_decoder else "  (tanpa aux decoder)")
          + f"  device: {device}")

    ctc_criterion = nn.CTCLoss(blank=0, zero_infinity=True)
    aux_criterion = nn.CrossEntropyLoss(ignore_index=AUX_PAD, label_smoothing=0.1) if aux_decoder else None

    params = list(model.parameters()) + (list(aux_decoder.parameters()) if aux_decoder else [])
    optimizer = torch.optim.Adam(params, lr=args.lr)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, make_lr_lambda(args.warmup_epochs, args.epochs))

    tag = f"w{args.width:.2f}" + (args.tag_suffix or "")
    ckpt_path = os.path.join(CKPT_DIR, f"crnn_{tag}_best.pt")
    log_path = os.path.join(LOG_DIR, f"crnn_{tag}.json")

    history = []
    best_val_cer = float("inf")
    epochs_no_improve = 0
    t_start = time.time()

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_ctc_loss, epoch_aux_loss = 0.0, 0.0
        n_batches = 0
        for batch in train_loader:
            (images, input_lengths, targets, target_lengths, _,
             aux_input, aux_target, aux_padding_mask) = batch
            images = images.to(device)
            targets = targets.to(device)
            input_lengths = input_lengths.to(device)
            target_lengths = target_lengths.to(device)

            log_probs = model(images)
            ctc_loss = ctc_criterion(log_probs, targets, input_lengths, target_lengths)
            loss = ctc_loss

            if aux_decoder is not None:
                aux_input = aux_input.to(device)
                aux_target = aux_target.to(device)
                aux_padding_mask = aux_padding_mask.to(device)
                memory = model.encode(images)  # (B, T, 2*hidden) -- shared representation
                aux_logits = aux_decoder(memory, aux_input, tgt_key_padding_mask=aux_padding_mask)
                aux_loss = aux_criterion(aux_logits.reshape(-1, aux_logits.size(-1)), aux_target.reshape(-1))
                loss = loss + args.aux_weight * aux_loss
                epoch_aux_loss += aux_loss.item()

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 5.0)
            optimizer.step()
            epoch_ctc_loss += ctc_loss.item()
            n_batches += 1

        scheduler.step()
        avg_ctc_loss = epoch_ctc_loss / max(1, n_batches)
        avg_aux_loss = epoch_aux_loss / max(1, n_batches)
        current_lr = optimizer.param_groups[0]["lr"]

        val_metrics = evaluate(model, val_loader, idx_to_symbol, device)
        elapsed = time.time() - t_start
        print(f"[width={args.width}] epoch {epoch}/{args.epochs}  lr={current_lr:.2e}  "
              f"ctc_loss={avg_ctc_loss:.4f}  aux_loss={avg_aux_loss:.4f}  "
              f"val_cer={val_metrics['cer']:.4f}  val_wer={val_metrics['wer']:.4f}  "
              f"val_exact={val_metrics['exact_match']:.4f}  ({elapsed:.0f}s elapsed)")

        history.append({"epoch": epoch, "ctc_loss": avg_ctc_loss, "aux_loss": avg_aux_loss,
                         "lr": current_lr, **val_metrics, "elapsed_s": elapsed})
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({"width_mult": args.width, "n_params": n_params, "use_aux": args.use_aux,
                       "aux_params": aux_params, "history": history}, f, indent=1)

        if val_metrics["cer"] < best_val_cer:
            best_val_cer = val_metrics["cer"]
            epochs_no_improve = 0
            torch.save({"model_state": model.state_dict(), "width_mult": args.width,
                        "n_params": n_params, "epoch": epoch, "val_cer": best_val_cer,
                        "use_aux": args.use_aux}, ckpt_path)
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= args.patience:
                print(f"[width={args.width}] early stop di epoch {epoch} (tidak membaik {args.patience}x)")
                break

    print(f"[width={args.width}] selesai. Best val CER: {best_val_cer:.4f} -> {ckpt_path}")

    # final test-set evaluation using the best (lowest val CER) checkpoint --
    # CTC-only path, exactly as the model would be deployed.
    best = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(best["model_state"])
    test_metrics = evaluate(model, test_loader, idx_to_symbol, device)
    print(f"[width={args.width}] TEST: cer={test_metrics['cer']:.4f} wer={test_metrics['wer']:.4f} "
          f"exact={test_metrics['exact_match']:.4f} (n={test_metrics['n']})")

    test_log_path = os.path.join(LOG_DIR, f"crnn_{tag}_test.json")
    with open(test_log_path, "w", encoding="utf-8") as f:
        json.dump({"width_mult": args.width, "n_params": n_params, "use_aux": args.use_aux,
                   "best_epoch": best["epoch"], **test_metrics}, f, indent=1)


if __name__ == "__main__":
    main()
