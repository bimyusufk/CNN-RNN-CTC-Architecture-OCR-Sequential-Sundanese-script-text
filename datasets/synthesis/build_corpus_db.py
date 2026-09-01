# -*- coding: utf-8 -*-
"""One-time migration: consolidate manifest.csv, vocab.json, the (now
stale) pilot manifest files, the NusaAksara parquet, and every past
training run's JSON log into a single SQLite database (corpus.db) --
the single source of truth this project's data has been missing.

Read-only against everything except corpus.db itself. Does not touch
manifest.csv/vocab.json/images/ or anything the currently-running
training process depends on -- training only ever reads those files
ONCE at startup into memory, so this script running alongside it is
safe (confirmed before running this).

After this, manifest.csv/vocab.json become EXPORTS generated from the
database (see export_manifest.py), not hand-maintained files.

Usage:
    python datasets/synthesis/build_corpus_db.py
"""
import csv
import json
import os
import re
import sqlite3
import subprocess
from collections import defaultdict

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(ROOT))
IMAGES_DIR = os.path.join(ROOT, "images")
MANIFEST = os.path.join(ROOT, "manifest.csv")
VOCAB = os.path.join(ROOT, "vocab.json")
PARQUET = os.path.join(REPO, "datasets", "nusaaksara_corpus", "transcription_transliteration.parquet")
PILOT_PROKLAMASI = os.path.join(ROOT, "pilot_proklamasi_manifest.csv")
PILOT_HISTORY = os.path.join(ROOT, "history_corpus_manifest.csv")
TRAINING_LOGS = os.path.join(REPO, "training", "logs")
DB_PATH = os.path.join(ROOT, "corpus.db")

INPUT_HEIGHT = 32
SYMBOL_CAP = 250    # threshold applied during the bigcorpus2 filter pass
PIXEL_CAP = 2000    # threshold applied during the bigcorpus3 filter pass (resized width)

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE source_batches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL CHECK(source_type IN ('native','mt_translated')),
    mt_system TEXT,
    origin_description TEXT,
    script_name TEXT,
    git_commit TEXT,
    review_status TEXT NOT NULL DEFAULT 'not_reviewed'
        CHECK(review_status IN ('not_reviewed','in_review','reviewed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);

CREATE TABLE sentences (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES source_batches(id),
    source_file TEXT,
    id_sentence TEXT,
    su_sentence TEXT,
    label TEXT NOT NULL,
    n_symbols INTEGER NOT NULL,
    split TEXT NOT NULL CHECK(split IN ('train','val','test')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','excluded_symbol_cap','excluded_pixel_cap',
                          'excluded_render_failure','excluded_untranslated',
                          'excluded_non_latin_script','pending_review',
                          'reviewed_accepted','reviewed_rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_sentences_split_status ON sentences(split, status);
CREATE INDEX idx_sentences_batch ON sentences(batch_id);

CREATE TABLE images (
    id INTEGER PRIMARY KEY,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id),
    filename TEXT NOT NULL UNIQUE,
    render_index INTEGER NOT NULL DEFAULT 0,
    width_px INTEGER,
    height_px INTEGER,
    resized_width_px INTEGER,
    crop_pool TEXT CHECK(crop_pool IN ('train','eval')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_images_sentence ON images(sentence_id);

CREATE TABLE vocab_symbols (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    first_seen_batch_id INTEGER REFERENCES source_batches(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE filter_events (
    id INTEGER PRIMARY KEY,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id),
    event_type TEXT NOT NULL,
    threshold_value TEXT,
    reason_detail TEXT,
    script_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_filter_events_sentence ON filter_events(sentence_id);

CREATE TABLE training_runs (
    id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL UNIQUE,
    width_mult REAL NOT NULL,
    use_aux INTEGER,
    use_augment INTEGER,
    n_train INTEGER, n_val INTEGER, n_test INTEGER, vocab_size INTEGER,
    batch_size INTEGER,
    git_commit TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    best_epoch INTEGER,
    best_val_cer REAL,
    test_cer REAL, test_wer REAL, test_exact_match REAL,
    checkpoint_path TEXT,
    notes TEXT
);
"""


def git_commit_hash():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=5)
        return out.stdout.strip()[:12] if out.returncode == 0 else None
    except Exception:
        return None


def resized_width(path):
    with Image.open(path) as img:
        w, h = img.size
    return max(4, round(w * INPUT_HEIGHT / h)), w, h


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    commit = git_commit_hash()

    # --- 1. source_batches ---
    batches = {
        "nusaaksara_v1": ("native", None,
                           "801 kalimat cerita rakyat Sunda dari korpus NusaAksara (Adilazuarda et al., 2025)",
                           "build_dataset.py"),
        "proklamasi_googletranslate": ("mt_translated", "Google Translate",
                                        "Dokumen Proklamasi Kemerdekaan Indonesia, diterjemahkan ID->SU",
                                        "synthesize_proklamasi.py"),
        "history_corpus_nllb600m": ("mt_translated", "NLLB-200-distilled-600M",
                                     "50 artikel sejarah Wikipedia Indonesia (prasejarah-kolonial), diterjemahkan ID->SU",
                                     "synthesize_history_corpus.py"),
    }
    batch_id = {}
    for name, (stype, mt, desc, script) in batches.items():
        cur = conn.execute(
            "INSERT INTO source_batches (name, source_type, mt_system, origin_description, script_name, git_commit) "
            "VALUES (?,?,?,?,?,?)", (name, stype, mt, desc, script, commit))
        batch_id[name] = cur.lastrowid

    # --- 2. NusaAksara su_sentence lookup (row_idx -> latin text) ---
    id_to_su = {}
    try:
        import pandas as pd
        df = pd.read_parquet(PARQUET)
        df = df[df["script"] == "sunda"].reset_index(drop=True)
        for row_idx, row in df.iterrows():
            id_to_su[row_idx] = row["transliteration"]
    except Exception as e:
        print(f"WARNING: could not load parquet for su_sentence lookup: {e}")

    # --- 3. pilot manifest lookups (filename -> su_sentence, source_file) ---
    def load_pilot(path):
        lookup = {}
        if not os.path.exists(path):
            return lookup
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lookup[r["filename"]] = (r.get("latin_source", ""), r.get("source_file") or r.get("source_line", ""))
        return lookup

    pilot_p_lookup = load_pilot(PILOT_PROKLAMASI)
    pilot_h_lookup = load_pilot(PILOT_HISTORY)

    # --- 4. current (active) manifest rows ---
    active_filenames = set()
    active_rows = []
    with open(MANIFEST, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            active_filenames.add(r["filename"])
            active_rows.append(r)

    n_sentences = 0
    n_images = 0
    n_excluded = 0

    # --- 5. NusaAksara: group by (split, row_idx) -> one sentence, N images ---
    nusa_rows = [r for r in active_rows if not r["filename"].startswith(("pilot_proklamasi/", "history_corpus/"))]
    groups = defaultdict(list)
    for r in nusa_rows:
        groups[(r["split"], r["row_idx"])].append(r)

    for (split, row_idx), rows in groups.items():
        su = id_to_su.get(int(row_idx)) if row_idx.isdigit() else None
        label = rows[0]["label"]
        n_symbols = int(rows[0]["n_symbols"])
        cur = conn.execute(
            "INSERT INTO sentences (batch_id, source_file, su_sentence, label, n_symbols, split, status) "
            "VALUES (?,?,?,?,?,?,'active')",
            (batch_id["nusaaksara_v1"], f"nusaaksara_row_{row_idx}", su, label, n_symbols, split))
        sid = cur.lastrowid
        n_sentences += 1
        for ridx, r in enumerate(rows):
            path = os.path.join(IMAGES_DIR, r["filename"])
            rw, w, h = (resized_width(path) if os.path.exists(path) else (None, None, None))
            pool = "train" if split == "train" else "eval"
            conn.execute(
                "INSERT INTO images (sentence_id, filename, render_index, width_px, height_px, resized_width_px, crop_pool) "
                "VALUES (?,?,?,?,?,?,?)", (sid, r["filename"], ridx, w, h, rw, pool))
            n_images += 1

    # --- 6. pilot batches: each row is its own sentence, active or excluded ---
    def process_pilot(lookup, batch_key, prefix, split_for_active="train"):
        nonlocal n_sentences, n_images, n_excluded
        for fname, (su, source_file) in lookup.items():
            path = os.path.join(IMAGES_DIR, fname)
            if not os.path.exists(path):
                continue  # render itself failed originally; not a filter exclusion
            rw, w, h = resized_width(path)
            # recompute label/n_symbols isn't cheaply available for excluded
            # rows (label lives only in the manifest); approximate n_symbols
            # isn't needed for filter classification -- pixel width is.
            is_active = fname in active_filenames
            active_row = next((r for r in active_rows if r["filename"] == fname), None) if is_active else None
            label = active_row["label"] if active_row else ""
            n_symbols = int(active_row["n_symbols"]) if active_row else 0
            split = active_row["split"] if active_row else split_for_active
            status = "active" if is_active else (
                "excluded_pixel_cap" if rw > PIXEL_CAP else "excluded_symbol_cap")

            cur = conn.execute(
                "INSERT INTO sentences (batch_id, source_file, su_sentence, label, n_symbols, split, status) "
                "VALUES (?,?,?,?,?,?,?)",
                (batch_id[batch_key], source_file, su, label, n_symbols, split, status))
            sid = cur.lastrowid
            n_sentences += 1
            conn.execute(
                "INSERT INTO images (sentence_id, filename, render_index, width_px, height_px, resized_width_px, crop_pool) "
                "VALUES (?,?,0,?,?,?,'train')", (sid, fname, w, h, rw))
            n_images += 1

            if not is_active:
                n_excluded += 1
                conn.execute(
                    "INSERT INTO filter_events (sentence_id, event_type, threshold_value, reason_detail, script_name) "
                    "VALUES (?,?,?,?,?)",
                    (sid, status, str(PIXEL_CAP if status == "excluded_pixel_cap" else SYMBOL_CAP),
                     "Direkonstruksi dari lebar citra piksel saat migrasi ke DB (file asli masih ada di disk)",
                     "build_corpus_db.py"))

    process_pilot(pilot_p_lookup, "proklamasi_googletranslate", "pilot_proklamasi/")
    process_pilot(pilot_h_lookup, "history_corpus_nllb600m", "history_corpus/")

    # --- 7. vocab_symbols, attributed to first batch (by insertion order) containing them ---
    with open(VOCAB, encoding="utf-8") as f:
        vocab = json.load(f)
    for sym in vocab:
        row = conn.execute(
            "SELECT sb.id FROM sentences s JOIN source_batches sb ON s.batch_id=sb.id "
            "WHERE s.status='active' AND (' '||s.label||' ') LIKE ? ORDER BY sb.id LIMIT 1",
            (f"% {sym} %",)).fetchone()
        conn.execute("INSERT OR IGNORE INTO vocab_symbols (symbol, first_seen_batch_id) VALUES (?,?)",
                     (sym, row[0] if row else None))

    # --- 8. training_runs, from every existing logs/*.json + *_test.json pair ---
    n_runs = 0
    if os.path.isdir(TRAINING_LOGS):
        for fname in sorted(os.listdir(TRAINING_LOGS)):
            if not fname.endswith(".json") or fname.endswith("_test.json"):
                continue
            tag = fname[:-5]
            try:
                hist = json.load(open(os.path.join(TRAINING_LOGS, fname), encoding="utf-8"))
            except Exception:
                continue
            history = hist.get("history", [])
            if not history:
                continue
            best = min(history, key=lambda e: e.get("cer", 1.0))
            test_path = os.path.join(TRAINING_LOGS, tag + "_test.json")
            test = json.load(open(test_path, encoding="utf-8")) if os.path.exists(test_path) else {}
            conn.execute(
                "INSERT OR IGNORE INTO training_runs (tag, width_mult, use_aux, use_augment, n_train, n_val, n_test, "
                "vocab_size, best_epoch, best_val_cer, test_cer, test_wer, test_exact_match) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tag, hist.get("width_mult", 0), int(bool(hist.get("use_aux"))), None,
                 None, None, test.get("n"), hist.get("aux_params") and None,
                 best.get("epoch"), best.get("cer"),
                 test.get("cer"), test.get("wer"), test.get("exact_match")))
            n_runs += 1

    conn.commit()

    # --- sanity checks ---
    n_active_db = conn.execute("SELECT COUNT(*) FROM images i JOIN sentences s ON i.sentence_id=s.id "
                                "WHERE s.status='active'").fetchone()[0]
    n_manifest = len(active_rows)
    print(f"Sentences: {n_sentences}  (excluded: {n_excluded})")
    print(f"Images total: {n_images}")
    print(f"Images active in DB: {n_active_db}  vs manifest.csv rows: {n_manifest}  "
          f"{'OK, MATCH' if n_active_db == n_manifest else 'MISMATCH -- investigate'}")
    print(f"Vocab symbols: {len(vocab)}")
    print(f"Training runs recorded: {n_runs}")
    print(f"\nDatabase written to: {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
