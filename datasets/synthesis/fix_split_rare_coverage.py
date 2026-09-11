# -*- coding: utf-8 -*-
"""Patch corpus.db's split assignment so every symbol appearing anywhere
in the active corpus is guaranteed at least some representation in TRAIN
-- fixes the "0% accuracy, never seen in train" failure mode found by
stratified_cer.py (11 test-set symbol occurrences with zero train exposure,
caused by count-based split logic that doesn't know about symbol rarity).

Policy:
  - very rare (total occurrences < 20): ALL occurrences forced to train.
    Too few examples to evaluate meaningfully on val/test anyway.
  - rare (20-99): if train currently has 0 occurrences, move val/test
    sentences containing it into train until covered (does not evacipate
    val/test entirely -- only closes a true zero-coverage gap).
  - >=100: left untouched, already adequately covered per the stratified
    analysis (99%+ accuracy at that tier already).

EXCLUDES nusaaksara_v1 from patching: that batch's images were rendered
via build_dataset.py's crop_pool() mechanism, which draws train-split
sentences ONLY from a disjoint "train" physical crop pool and val/test
ONLY from a disjoint "eval" pool -- the split is baked into which pixels
exist on disk, not just a DB label. Flipping its `split` column post-hoc
without re-rendering would silently reintroduce crop-instance leakage.
The other batches (history_corpus_nllb600m, wikipedia_sunda,
budak_teuneung_fonts) render from an unrestricted pool / are font-
rendered, so no such constraint applies -- safe to repatch their split
label alone.
"""
import csv
import os
import sqlite3
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "corpus.db")

VERY_RARE = 20
RARE = 100
PATCHABLE_BATCHES = {"history_corpus_nllb600m", "wikipedia_sunda", "budak_teuneung_fonts",
                      "proklamasi_googletranslate"}


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    rows = conn.execute("""
        SELECT s.id, sb.name, s.label, s.split
        FROM sentences s JOIN source_batches sb ON s.batch_id = sb.id
        WHERE s.status='active'
    """).fetchall()

    global_freq = Counter()
    train_freq = Counter()
    for sid, batch, label, split in rows:
        syms = label.split(" ")
        global_freq.update(syms)
        if split == "train":
            train_freq.update(syms)

    # symbols needing intervention, in increasing order of rarity so the
    # rarest (most constrained) get first pick of available sentences
    protected = sorted(
        [s for s, c in global_freq.items() if c < RARE and s != "<sp>"],
        key=lambda s: global_freq[s]
    )

    # index: symbol -> list of (sentence_id, batch, current_split)
    sym_to_sentences = defaultdict(list)
    for sid, batch, label, split in rows:
        for sym in set(label.split(" ")):
            if sym in global_freq and global_freq[sym] < RARE:
                sym_to_sentences[sym].append((sid, batch, split))

    to_move_to_train = set()
    still_uncovered = []

    for sym in protected:
        total = global_freq[sym]
        target_tier = "very_rare" if total < VERY_RARE else "rare"
        current_train = train_freq[sym]

        candidates = [(sid, batch, split) for sid, batch, split in sym_to_sentences[sym]
                      if batch in PATCHABLE_BATCHES]
        non_train_candidates = [c for c in candidates if c[2] != "train"]

        if target_tier == "very_rare":
            # force ALL patchable occurrences to train
            for sid, batch, split in non_train_candidates:
                to_move_to_train.add(sid)
        else:
            # rare: only act if train coverage is currently zero
            if current_train == 0:
                if non_train_candidates:
                    # move just enough sentences to get nonzero coverage
                    # (move all candidate sentences containing it -- simplest
                    # correct fix, sentences are typically short so this
                    # rarely moves more than a couple)
                    for sid, batch, split in non_train_candidates:
                        to_move_to_train.add(sid)
                else:
                    still_uncovered.append(sym)  # only exists in nusaaksara_v1 val/test -- can't patch safely

    print(f"Simbol dilindungi (total <{RARE}, di luar <sp>): {len(protected)}")
    print(f"Kalimat yang akan dipindah ke train: {len(to_move_to_train)}")
    print(f"Simbol yang TETAP tidak tercakup (cuma ada di nusaaksara_v1 val/test, tidak dipatch demi menjaga crop-pool): {len(still_uncovered)}")
    if still_uncovered:
        for s in still_uncovered:
            print(f"  {s!r}")

    for sid in to_move_to_train:
        conn.execute("UPDATE sentences SET split='train' WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    print("\ncorpus.db diperbarui. Jalankan export_manifest.py untuk menyinkronkan manifest.csv.")


if __name__ == "__main__":
    main()
