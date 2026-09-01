# -*- coding: utf-8 -*-
"""Shared utilities: Levenshtein edit distance (no external dependency --
editdistance/python-Levenshtein failed to build here, no C compiler), CER/
WER, and vocabulary loading."""
import json
import os


def edit_distance(a, b):
    """Levenshtein distance between two sequences (lists or strings)."""
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m]


def cer(pred_symbols, true_symbols):
    """Character(symbol)-level error rate: edit_distance / len(true)."""
    if len(true_symbols) == 0:
        return 0.0 if len(pred_symbols) == 0 else 1.0
    return edit_distance(pred_symbols, true_symbols) / len(true_symbols)


def wer(pred_symbols, true_symbols):
    """Word error rate: split on the '<sp>' separator token, then edit
    distance over the resulting word lists (each word = tuple of symbols)."""
    def to_words(symbols):
        words, cur = [], []
        for s in symbols:
            if s == "<sp>":
                words.append(tuple(cur))
                cur = []
            else:
                cur.append(s)
        words.append(tuple(cur))
        return words

    pw, tw = to_words(pred_symbols), to_words(true_symbols)
    if len(tw) == 0:
        return 0.0 if len(pw) == 0 else 1.0
    return edit_distance(pw, tw) / len(tw)


def load_vocab(vocab_path):
    """Returns (symbol_to_idx, idx_to_symbol). Index 0 is reserved for the
    CTC blank token; real symbols start at 1."""
    with open(vocab_path, encoding="utf-8") as f:
        symbols = json.load(f)
    symbol_to_idx = {s: i + 1 for i, s in enumerate(symbols)}
    idx_to_symbol = {i + 1: s for i, s in enumerate(symbols)}
    return symbol_to_idx, idx_to_symbol


def ctc_greedy_decode(pred_indices, idx_to_symbol, blank=0):
    """Collapse a raw per-timestep argmax index sequence via the standard
    CTC rule: merge consecutive repeats, then drop blanks."""
    collapsed = []
    prev = None
    for idx in pred_indices:
        if idx != prev:
            collapsed.append(idx)
        prev = idx
    return [idx_to_symbol[i] for i in collapsed if i != blank and i in idx_to_symbol]
