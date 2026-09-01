# -*- coding: utf-8 -*-
"""Dataset/collate for the CRNN+CTC training set produced by
datasets/synthesis/build_dataset.py (manifest.csv + images/{split}/...).

Images are resized to height=32 (Tabel 3.1's fixed input height), width
scaled proportionally. Train-split labels are guaranteed in-vocabulary (the
vocab was built FROM train); val/test labels are kept as raw symbol
strings, since a handful contain OOV symbols (measured: val 0.9%, test
1.8% of symbol instances) that only matter for CER scoring, not for a
model target tensor."""
import csv
import os
import sys

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from model import INPUT_HEIGHT, AUX_PAD, AUX_BOS, AUX_EOS, ctc_ids_to_aux_ids

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "datasets", "synthesis"))
from augment import augment_image  # noqa: E402


def load_manifest(manifest_path):
    with open(manifest_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_image_tensor(img):
    """img: a path (str) or an already-opened PIL image."""
    if isinstance(img, str):
        img = Image.open(img).convert("L")
    w, h = img.size
    new_w = max(4, int(round(w * INPUT_HEIGHT / h)))
    img = img.resize((new_w, INPUT_HEIGHT), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32) / 255.0  # white=1.0, black=0.0
    return torch.from_numpy(arr).unsqueeze(0)  # (1, H, W)


class CRNNDataset(Dataset):
    def __init__(self, manifest_rows, images_dir, split, augment=False):
        """augment: apply on-the-fly rotation/scale/elastic-distortion
        augmentation (datasets/synthesis/augment.py) -- pass True ONLY for
        the train split. val/test must stay unaugmented so CER/WER measure
        true generalization, not robustness to the augmentation itself."""
        self.rows = [r for r in manifest_rows if r["split"] == split]
        self.images_dir = images_dir
        self.augment = augment

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        row = self.rows[i]
        path = os.path.join(self.images_dir, row["filename"])
        if self.augment:
            img = Image.open(path).convert("L")
            img = augment_image(img)
            tensor = load_image_tensor(img)
        else:
            tensor = load_image_tensor(path)
        labels = row["label"].split(" ") if row["label"] else []
        return tensor, labels, row["filename"]


def output_length(input_width):
    """Matches the model's width reduction exactly: only pool1 and pool2
    touch width (stride 2 each, floor division); pool3/pool4 are (2,1) and
    leave width unchanged."""
    w = input_width // 2
    w = w // 2
    return max(1, w)


class TrainCollate:
    """A class, not a closure -- Windows' spawn-based multiprocessing
    (num_workers>0) needs the collate_fn to be picklable to hand it to
    worker processes, and a nested/local function (the previous
    make_train_collate(...) -> def collate(...) pattern) can't be pickled.
    A class with picklable instance attributes (symbol_to_idx, a plain
    str->int dict) works fine."""

    def __init__(self, symbol_to_idx):
        self.symbol_to_idx = symbol_to_idx

    def __call__(self, batch):
        symbol_to_idx = self.symbol_to_idx
        tensors, labels_list, _ = zip(*batch)
        widths = [t.shape[-1] for t in tensors]
        max_w = max(widths)
        batch_size = len(tensors)
        padded = torch.ones(batch_size, 1, INPUT_HEIGHT, max_w)  # pad with white
        for i, t in enumerate(tensors):
            padded[i, :, :, :t.shape[-1]] = t

        input_lengths = torch.tensor([output_length(w) for w in widths], dtype=torch.long)
        target_ids = []
        target_lengths = []
        per_sample_ctc_ids = []
        for labels in labels_list:
            ids = [symbol_to_idx[s] for s in labels]
            per_sample_ctc_ids.append(ids)
            target_ids.extend(ids)
            target_lengths.append(len(ids))
        targets = torch.tensor(target_ids, dtype=torch.long)
        target_lengths = torch.tensor(target_lengths, dtype=torch.long)

        # --- auxiliary decoder teacher-forcing tensors (training-only) ---
        # aux_input:  [BOS, s1, s2, ..., sn]      (decoder input)
        # aux_target: [s1, s2, ..., sn, EOS]       (what it must predict)
        aux_seqs = [ctc_ids_to_aux_ids(ids) for ids in per_sample_ctc_ids]
        max_len = max(len(s) for s in aux_seqs) + 1  # +1 for BOS/EOS
        aux_input = torch.full((batch_size, max_len), AUX_PAD, dtype=torch.long)
        aux_target = torch.full((batch_size, max_len), AUX_PAD, dtype=torch.long)
        aux_padding_mask = torch.ones(batch_size, max_len, dtype=torch.bool)
        for i, seq in enumerate(aux_seqs):
            L = len(seq)
            aux_input[i, 0] = AUX_BOS
            aux_input[i, 1:1 + L] = torch.tensor(seq, dtype=torch.long)
            aux_target[i, 0:L] = torch.tensor(seq, dtype=torch.long)
            aux_target[i, L] = AUX_EOS
            aux_padding_mask[i, :L + 1] = False  # False = not padding (real token)

        return (padded, input_lengths, targets, target_lengths, labels_list,
                aux_input, aux_target, aux_padding_mask)


def eval_collate(batch):
    """Batch size is expected to be 1 for eval (simplest correct handling
    of variable width + possible OOV symbols); kept generic just in case."""
    tensors, labels_list, filenames = zip(*batch)
    widths = [t.shape[-1] for t in tensors]
    max_w = max(widths)
    batch_size = len(tensors)
    padded = torch.ones(batch_size, 1, INPUT_HEIGHT, max_w)
    for i, t in enumerate(tensors):
        padded[i, :, :, :t.shape[-1]] = t
    input_lengths = torch.tensor([output_length(w) for w in widths], dtype=torch.long)
    return padded, input_lengths, labels_list, filenames
