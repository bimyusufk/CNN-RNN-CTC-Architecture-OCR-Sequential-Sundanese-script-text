#!/bin/bash
# Retry after fixing the --init-from vocab-growth bug (fc layer size
# mismatch) in train_crnn.py. Unlike queue_finalrun.sh, this checks exit
# codes and stops with a clear failure marker instead of silently
# cascading through fake "selesai" lines on a crash. DB merge/manifest
# export already happened (queue_finalrun.sh's first half succeeded) --
# this starts straight from training.
cd "$(dirname "$0")"
QLOG="queue_finalrun2.log"

echo "$(date '+%F %T') mulai fine-tune width=0.50 dari bigcorpus3 (retry setelah fix)" >> "$QLOG"
python train_crnn.py --width 0.50 --epochs 25 --warmup-epochs 3 --patience 10 \
  --use-aux --augment --batch-size 16 \
  --init-from checkpoints/crnn_w0.50_bigcorpus3_best.pt \
  --tag-suffix _finalcorpus >> "$QLOG" 2>&1
if [ $? -ne 0 ]; then
  echo "$(date '+%F %T') GAGAL width=0.50 finalcorpus -- BERHENTI, width=1.00 TIDAK dijalankan" >> "$QLOG"
  exit 1
fi
echo "$(date '+%F %T') width=0.50 finalcorpus SELESAI (berhasil)" >> "$QLOG"

echo "$(date '+%F %T') mulai fine-tune width=1.00 dari bigcorpus3" >> "$QLOG"
python train_crnn.py --width 1.00 --epochs 25 --warmup-epochs 3 --patience 10 \
  --use-aux --augment --batch-size 16 \
  --init-from checkpoints/crnn_w1.00_bigcorpus3_best.pt \
  --tag-suffix _finalcorpus >> "$QLOG" 2>&1
if [ $? -ne 0 ]; then
  echo "$(date '+%F %T') GAGAL width=1.00 finalcorpus" >> "$QLOG"
  exit 1
fi
echo "$(date '+%F %T') width=1.00 finalcorpus SELESAI (berhasil) -- SEMUA SELESAI" >> "$QLOG"
