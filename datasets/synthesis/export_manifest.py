# -*- coding: utf-8 -*-
"""Regenerate manifest.csv and vocab.json FROM corpus.db -- after the
migration, the database is the source of truth; these files become
generated exports (kept because the training pipeline and quick manual
inspection still read plain CSV/JSON, not because they're authoritative).

Run this after any curation change to corpus.db (new batch added, a
filter applied, statuses updated) to bring manifest.csv/vocab.json back
in sync.

Usage:
    python datasets/synthesis/export_manifest.py
"""
import csv
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "corpus.db")
MANIFEST_OUT = os.path.join(ROOT, "manifest.csv")
VOCAB_OUT = os.path.join(ROOT, "vocab.json")


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT i.filename, s.split, s.label, s.n_symbols
        FROM images i JOIN sentences s ON i.sentence_id = s.id
        WHERE s.status = 'active'
        ORDER BY s.split, i.filename
    """).fetchall()

    with open(MANIFEST_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "split", "row_idx", "label", "n_symbols"])
        for filename, split, label, n_symbols in rows:
            writer.writerow([filename, split, "", label, n_symbols])

    vocab_rows = conn.execute("""
        SELECT DISTINCT symbol FROM vocab_symbols v
        WHERE EXISTS (
            SELECT 1 FROM sentences s
            WHERE s.status='active' AND s.split='train'
              AND (' '||s.label||' ') LIKE '% '||v.symbol||' %'
        )
        ORDER BY symbol
    """).fetchall()
    vocab = sorted(v[0] for v in vocab_rows)
    with open(VOCAB_OUT, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=1)

    print(f"Exported {len(rows)} image rows -> {MANIFEST_OUT}")
    print(f"Exported {len(vocab)} vocab symbols -> {VOCAB_OUT}")
    conn.close()


if __name__ == "__main__":
    main()
