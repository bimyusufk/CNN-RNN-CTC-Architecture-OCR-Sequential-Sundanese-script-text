# -*- coding: utf-8 -*-
"""Supplementary profiler: num_workers sweep specifically WITH augment=True
(the condition we'll actually deploy -- augmentation stays on because
it's proven to help generalization; this just finds the worker count
that keeps the GPU fed under that real CPU cost), aux=True (also the
config we'll deploy -- see profile_speed.py's Stage A for why aux isn't
being dropped just because it's not free)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_speed import time_config
import torch


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}\n")
    print("=== num_workers sweep, augment=True aux=True, batch=32 ===", flush=True)
    results = {}
    for nw in [4, 8, 12, 16, 24, 31]:
        rate = time_config(32, nw, True, True, device)
        results[nw] = rate
        print(f"  workers={nw:2}  ->  {rate:.2f} img/s", flush=True)
    best_nw = max(results, key=results.get)
    print(f"\nBest num_workers (augment=True, aux=True, batch=32): {best_nw} ({results[best_nw]:.2f} img/s)")

    print("\n=== batch_size sweep at best num_workers, augment=True aux=True ===", flush=True)
    results2 = {}
    for bs in [16, 32, 48, 64]:
        rate = time_config(bs, best_nw, True, True, device)
        results2[bs] = rate
        print(f"  batch={bs:3}  ->  {rate:.2f} img/s", flush=True)
    best_bs = max(results2, key=results2.get)
    print(f"\nBest batch_size: {best_bs} ({results2[best_bs]:.2f} img/s)")
    print(f"\nFINAL: batch_size={best_bs}, num_workers={best_nw}")


if __name__ == "__main__":
    main()
