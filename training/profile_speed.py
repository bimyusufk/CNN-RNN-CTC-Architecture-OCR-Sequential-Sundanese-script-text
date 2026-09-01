# -*- coding: utf-8 -*-
"""Quick throughput profiler: times N training BATCHES (not full epochs --
epochs on the merged corpus now take 400-650s, too slow to iterate on)
under different configs, to find what actually drives cost before
committing to a full training run.

Stage A: isolate which factor matters (augment on/off x aux-decoder
on/off), batch_size/workers fixed.
Stage B: grid batch_size x num_workers using the winning Stage-A config.
"""
import itertools
import os
import sys
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset import CRNNDataset, load_manifest, TrainCollate
from model import CRNN, AuxDecoder, LSTM_HIDDEN, ctc_ids_to_aux_ids, AUX_SPECIAL_TOKENS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYN_DIR = os.path.join(ROOT, "datasets", "synthesis")
MANIFEST_PATH = os.path.join(SYN_DIR, "manifest.csv")
VOCAB_PATH = os.path.join(SYN_DIR, "vocab.json")
IMAGES_DIR = os.path.join(SYN_DIR, "images")

N_BATCHES = 15
WARMUP = 3


def load_vocab():
    import json
    symbols = json.load(open(VOCAB_PATH, encoding="utf-8"))
    symbol_to_idx = {s: i + 1 for i, s in enumerate(symbols)}  # 0 = CTC blank
    return symbol_to_idx


def time_config(batch_size, num_workers, augment, use_aux, device):
    manifest = load_manifest(MANIFEST_PATH)
    symbol_to_idx = load_vocab()
    num_classes = len(symbol_to_idx) + 1
    aux_vocab_size = len(symbol_to_idx) + AUX_SPECIAL_TOKENS

    train_ds = CRNNDataset(manifest, IMAGES_DIR, "train", augment=augment)
    loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                         collate_fn=TrainCollate(symbol_to_idx),
                         num_workers=num_workers,
                         persistent_workers=(num_workers > 0))

    model = CRNN(num_classes, width_mult=0.50).to(device)
    aux_decoder = AuxDecoder(memory_dim=LSTM_HIDDEN * 2, aux_vocab_size=aux_vocab_size).to(device) if use_aux else None
    ctc_loss_fn = nn.CTCLoss(blank=0, zero_infinity=True)
    ce_loss_fn = nn.CrossEntropyLoss(ignore_index=0, label_smoothing=0.1)
    params = list(model.parameters()) + (list(aux_decoder.parameters()) if aux_decoder else [])
    opt = torch.optim.Adam(params, lr=1e-3)

    it = iter(loader)
    times = []
    n_images = 0
    for i in range(WARMUP + N_BATCHES):
        t0 = time.time()
        batch = next(it)
        images, input_lengths, targets, target_lengths, labels_list, aux_input, aux_target, aux_padding_mask = batch
        images = images.to(device)
        targets = targets.to(device)
        input_lengths = input_lengths.to(device)
        target_lengths = target_lengths.to(device)

        opt.zero_grad()
        if use_aux:
            memory = model.encode(images)
            log_probs = torch.log_softmax(model.fc(memory), dim=2).permute(1, 0, 2)
        else:
            log_probs = model(images)
        ctc_loss = ctc_loss_fn(log_probs, targets, input_lengths, target_lengths)
        loss = ctc_loss
        if use_aux:
            aux_input_d = aux_input.to(device)
            aux_target_d = aux_target.to(device)
            aux_mask_d = aux_padding_mask.to(device)
            aux_logits = aux_decoder(memory, aux_input_d, tgt_key_padding_mask=aux_mask_d)
            aux_loss = ce_loss_fn(aux_logits.reshape(-1, aux_logits.size(-1)), aux_target_d.reshape(-1))
            loss = loss + aux_loss
        loss.backward()
        opt.step()
        if device.type == "cuda":
            torch.cuda.synchronize()

        dt = time.time() - t0
        if i >= WARMUP:
            times.append(dt)
            n_images += images.size(0)

    del loader, it
    total_t = sum(times)
    return n_images / total_t  # images/sec


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}\n")

    print("=== Stage A: isolate augment / aux-decoder cost (batch=32, workers=8) ===", flush=True)
    stage_a_results = {}
    for augment, use_aux in itertools.product([True, False], [True, False]):
        rate = time_config(32, 8, augment, use_aux, device)
        stage_a_results[(augment, use_aux)] = rate
        print(f"  augment={augment!s:5}  aux={use_aux!s:5}  ->  {rate:.2f} img/s", flush=True)

    best_aug, best_aux = max(stage_a_results, key=stage_a_results.get)
    print(f"\nFastest Stage-A combo: augment={best_aug}, aux={best_aux} "
          f"({stage_a_results[(best_aug, best_aux)]:.2f} img/s)\n")

    print(f"=== Stage B: batch_size x num_workers grid (augment={best_aug}, aux={best_aux}) ===", flush=True)
    stage_b_results = {}
    for bs, nw in itertools.product([16, 32, 64, 96], [4, 8, 16, 24]):
        try:
            rate = time_config(bs, nw, best_aug, best_aux, device)
        except Exception as e:
            print(f"  batch={bs:3} workers={nw:2}  ->  FAILED ({e})", flush=True)
            continue
        stage_b_results[(bs, nw)] = rate
        print(f"  batch={bs:3} workers={nw:2}  ->  {rate:.2f} img/s", flush=True)

    best_bs, best_nw = max(stage_b_results, key=stage_b_results.get)
    print(f"\nFastest overall: batch_size={best_bs}, num_workers={best_nw}, "
          f"augment={best_aug}, aux={best_aux} ({stage_b_results[(best_bs, best_nw)]:.2f} img/s)")

    print("\nRESULT_LINE " + str({
        "batch_size": best_bs, "num_workers": best_nw, "augment": best_aug, "aux": best_aux,
        "rate": stage_b_results[(best_bs, best_nw)],
    }))


if __name__ == "__main__":
    main()
