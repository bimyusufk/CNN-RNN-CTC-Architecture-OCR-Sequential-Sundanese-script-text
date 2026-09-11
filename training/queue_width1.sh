#!/bin/bash
# Waits for the currently-running crnn_w0.50_bigcorpus3 job to finish (or
# crash/stall), then launches a width=1.00 run on the SAME (bigger, 7000+
# sentence) corpus to test whether the extra data now lets a wider model
# generalize better than it did on the old 801-sentence corpus (where 0.50
# beat 0.75/1.00/1.50, attributed to overfitting without an LR scheduler).
# Never touches the running process -- polls its own JSON log file only.
cd "$(dirname "$0")"

TEST_LOG="logs/crnn_w0.50_bigcorpus3_test.json"
TRAIN_LOG="logs/crnn_w0.50_bigcorpus3.json"
QLOG="queue_width1.log"

last_epoch=-1
stale_checks=0
STALE_LIMIT=20   # 20 * 60s = 20 min with no new epoch => treat as dead/crashed

echo "$(date '+%F %T') menunggu crnn_w0.50_bigcorpus3 selesai..." >> "$QLOG"

while true; do
  if [ -f "$TEST_LOG" ]; then
    echo "$(date '+%F %T') width=0.50 selesai normal (test log ditemukan)" >> "$QLOG"
    break
  fi
  cur_epoch=$(python -c "
import json
try:
    with open('$TRAIN_LOG', encoding='utf-8') as f:
        d = json.load(f)
    print(d['history'][-1]['epoch'])
except Exception:
    print(-1)
" 2>/dev/null)
  if [ "$cur_epoch" = "$last_epoch" ]; then
    stale_checks=$((stale_checks + 1))
  else
    stale_checks=0
    last_epoch=$cur_epoch
  fi
  if [ "$stale_checks" -ge "$STALE_LIMIT" ]; then
    echo "$(date '+%F %T') tidak ada progres epoch selama ~20 menit (epoch terakhir=$last_epoch) -- anggap proses berhenti/crash, lanjut ke width=1.00" >> "$QLOG"
    break
  fi
  sleep 60
done

echo "$(date '+%F %T') memulai training width=1.00 (bigcorpus3, epochs=70)" >> "$QLOG"
python train_crnn.py --width 1.00 --epochs 70 --warmup-epochs 5 --patience 20 \
  --use-aux --augment --batch-size 16 --tag-suffix _bigcorpus3 >> "$QLOG" 2>&1
echo "$(date '+%F %T') width=1.00 selesai" >> "$QLOG"
