# -*- coding: utf-8 -*-
"""TensorBoard side-car: watches a train_crnn.py JSON log file (written
incrementally, one entry appended per epoch -- confirmed in the training
loop) and mirrors new epochs into TensorBoard scalar events. Runs as a
fully separate process; never touches the live training run, so it's
safe to attach to (or detach from) an already-running job without any
risk of interrupting it.

Usage:
    python tb_sidecar.py <path-to-json-log> [--tag NAME] [--poll-sec 5]
Then:
    tensorboard --logdir runs
"""
import argparse
import json
import os
import time

from torch.utils.tensorboard import SummaryWriter

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(ROOT, "runs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--tag", default=None, help="run name under runs/ (default: json filename stem)")
    ap.add_argument("--poll-sec", type=float, default=5.0)
    args = ap.parse_args()

    tag = args.tag or os.path.splitext(os.path.basename(args.json_path))[0]
    writer = SummaryWriter(log_dir=os.path.join(RUNS_DIR, tag))
    print(f"Watching {args.json_path}")
    print(f"Writing TensorBoard events to {os.path.join(RUNS_DIR, tag)}")

    n_written = 0
    while True:
        if os.path.exists(args.json_path):
            try:
                with open(args.json_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, ValueError):
                # file mid-write (training process is writing it right now) -- skip this poll
                time.sleep(args.poll_sec)
                continue

            history = data.get("history", [])
            for entry in history[n_written:]:
                epoch = entry["epoch"]
                for key in ("ctc_loss", "aux_loss", "lr", "cer", "wer", "exact_match", "train_loss"):
                    if key in entry:
                        writer.add_scalar(f"train/{key}" if key in ("ctc_loss", "aux_loss", "lr", "train_loss")
                                           else f"val/{key}", entry[key], epoch)
                writer.flush()
                print(f"  logged epoch {epoch}", flush=True)
            n_written = len(history)

        time.sleep(args.poll_sec)


if __name__ == "__main__":
    main()
