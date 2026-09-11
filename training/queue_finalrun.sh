#!/bin/bash
# Overnight pipeline: wait for wikipedia_sunda synthesis -> merge into
# corpus.db -> re-export manifest -> fine-tune width=0.50 then width=1.00
# from their existing bigcorpus3 checkpoints, on the expanded corpus with
# the new augmentation (mark/gap jitter at synthesis time, perspective/
# page-curve/paper-texture on-the-fly) active.
cd "$(dirname "$0")"
QLOG="queue_finalrun.log"
SCRATCH="C:/Users/UNPAD-~1/AppData/Local/Temp/claude/c--Users-Unpad-hci-Documents-TopoGrad-Net-New-Lightweight-OCR-Model/70f34ece-a65e-4769-b1f0-1e9ec21ccd33/scratchpad"
SYN_LOG="$SCRATCH/synth_wikisu.log"

echo "$(date '+%F %T') menunggu sintesis wikipedia_sunda selesai..." >> "$QLOG"
while ! grep -q "^Manifest:" "$SYN_LOG" 2>/dev/null; do
  sleep 15
done
echo "$(date '+%F %T') sintesis selesai, gabung ke corpus.db" >> "$QLOG"

python "$SCRATCH/add_wikipedia_sunda_batch.py" >> "$QLOG" 2>&1
python "../datasets/synthesis/export_manifest.py" >> "$QLOG" 2>&1

echo "$(date '+%F %T') mulai fine-tune width=0.50 dari bigcorpus3" >> "$QLOG"
python train_crnn.py --width 0.50 --epochs 25 --warmup-epochs 3 --patience 10 \
  --use-aux --augment --batch-size 16 \
  --init-from checkpoints/crnn_w0.50_bigcorpus3_best.pt \
  --tag-suffix _finalcorpus >> "$QLOG" 2>&1
echo "$(date '+%F %T') width=0.50 finalcorpus selesai" >> "$QLOG"

echo "$(date '+%F %T') mulai fine-tune width=1.00 dari bigcorpus3" >> "$QLOG"
python train_crnn.py --width 1.00 --epochs 25 --warmup-epochs 3 --patience 10 \
  --use-aux --augment --batch-size 16 \
  --init-from checkpoints/crnn_w1.00_bigcorpus3_best.pt \
  --tag-suffix _finalcorpus >> "$QLOG" 2>&1
echo "$(date '+%F %T') width=1.00 finalcorpus selesai -- SEMUA SELESAI" >> "$QLOG"
