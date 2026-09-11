# -*- coding: utf-8 -*-
"""Generalized Aksara Sunda word/sentence compositor -- takes real Unicode
Sundanese script text (not a hardcoded per-word syllable list like
demo_sentence.py/demo_paragraph.py) and composites it from real collected
crops (swara/ngalagena source data + hand-drawn rarangken), positioning
every mark using offsets measured live from the font's own GPOS geometry.

Pipeline for one syllable (base + 0..N marks):
  1. Shape base+marks with GSUB ligature features disabled (liga/ccmp/rlig/
     clig/rclt/calt) so HarfBuzz falls back to real mark-to-mark GPOS
     positioning instead of collapsing to a single composed ligature glyph.
  2. Identify which output glyph is the base by matching its glyph ID
     against a lone shaping of the base character (robust to panéléng,
     the one rarangken that reorders BEFORE its base in the glyph stream --
     it's the only one in the "di hareup"/front position category).
  3. The remaining glyphs, in output order, are taken to correspond to the
     input marks in input order (holds for every 1- and 2-mark case tested
     so far; flagged via ValueError if the count doesn't match, rather than
     silently mispositioning an unverified combination).
  4. Convert each glyph's absolute box to an offset relative to the base
     box (dx_frac, dy_frac, scale), cached by (base_cp, mark_cps) so a
     given combination is only measured once per process.
  5. Paste real crops using those offsets via paste_mark() from
     demo_sentence.py (stroke-matched at native resolution, antialiased,
     single deferred threshold -- see that module for why).

Usage:
    from compositor import render_text
    img = render_text("ᮊᮥᮙᮠ ᮓᮙᮀ")   # -> PIL 'L' image, or None if blank
"""
import os
import random

import uharfbuzz as hb
import freetype
from PIL import Image

from glyph_render import FONT_PATH
from demo_sentence import (
    load_random_crop, tight_ink, paste_mark, estimate_stroke_width,
    SYLLABLE_H, GAP_SYLLABLE, GAP_WORD,
)

ROOT = os.path.dirname(os.path.abspath(__file__))

# --- per-mark positional augmentation (synthesis-time, not on-the-fly) ----
# Small random perturbation of each rarangken's measured (dx_frac, dy_frac,
# scale) offset + a small rotation, applied fresh every render (unlike the
# cached base offsets, which stay fixed per base+mark combination). Purpose:
# real handwriting doesn't attach marks at one exact fixed spot -- the
# measured-from-font offsets give a realistic but rigid target, so every
# instance of e.g. "ka+u" currently looks identically positioned. Bounds
# are deliberately small relative to each syllable's own working canvas
# (canvas_w/h = ~2-3x the base's own size, see make_syllable_generic) --
# there is ~0.5-1.0x bw/bh of headroom before a mark would even approach
# its own canvas edge, let alone the neighboring syllable (GAP_SYLLABLE=6px
# only matters after tight-cropping). The binding constraint is NOT
# neighbor-bleeding (lots of headroom there) but the mark staying legibly
# attached to (and identifiable as) itself -- kept conservative for that
# reason, well inside the safe margin above.
MARK_JITTER_ENABLED = True
MARK_JITTER_POS = 0.04       # +/- fraction of base bw/bh added to dx_frac/dy_frac
MARK_JITTER_SCALE = 0.06     # +/- fractional scale multiplier (like augment.py's whole-image 0.92-1.08, slightly tighter)
MARK_JITTER_ROTATE_DEG = 3.0 # +/- degrees; new capability, kept <= the whole-image cap since a lone mark's shape identity is more sensitive to rotation than a full line


# --- inter-syllable / inter-word spacing jitter (synthesis-time) ---------
# Complements the mark-position jitter above: GAP_SYLLABLE/GAP_WORD are
# otherwise fixed (6px / 40px, at SYLLABLE_H=260 working resolution) for
# EVERY gap in EVERY sentence -- real handwriting doesn't space characters
# with pixel-perfect uniformity. Each gap is jittered independently (not
# one draw applied uniformly across the whole sentence), so spacing varies
# gap-to-gap the way real handwriting does. Bounds keep the two gap KINDS
# clearly separated -- max jittered syllable-gap (9px) stays well below
# min jittered word-gap (28px) -- so a syllable gap can never be mistaken
# for a word gap or vice versa.
GAP_JITTER_ENABLED = True
GAP_SYLLABLE_JITTER_FRAC = 0.5   # 6px -> 3-9px
GAP_WORD_JITTER_FRAC = 0.3       # 40px -> 28-52px


def _jittered_gap(base_gap, frac):
    if not GAP_JITTER_ENABLED:
        return base_gap
    return base_gap * random.uniform(1 - frac, 1 + frac)


def _jitter_mark_placement(offset):
    """offset: (dx_frac, dy_frac, scale) measured from font geometry.
    Returns (jittered_offset, rotate_deg) -- disabled (returns offset
    unchanged, rotate_deg=0.0) via MARK_JITTER_ENABLED for easy rollback
    during visual validation."""
    if not MARK_JITTER_ENABLED:
        return offset, 0.0
    dx_frac, dy_frac, scale = offset
    dx_frac = dx_frac + random.uniform(-MARK_JITTER_POS, MARK_JITTER_POS)
    dy_frac = dy_frac + random.uniform(-MARK_JITTER_POS, MARK_JITTER_POS)
    scale = scale * random.uniform(1 - MARK_JITTER_SCALE, 1 + MARK_JITTER_SCALE)
    rotate_deg = random.uniform(-MARK_JITTER_ROTATE_DEG, MARK_JITTER_ROTATE_DEG)
    return (dx_frac, dy_frac, scale), rotate_deg

# --- Unicode codepoint -> local dataset class name ------------------------

SWARA = {
    0x1B83: "swara_a", 0x1B84: "swara_i", 0x1B85: "swara_u",
    0x1B86: "swara_e_taling", 0x1B87: "swara_o", 0x1B88: "swara_e",
    0x1B89: "swara_eu",
}
NGALAGENA = {
    0x1B8A: "ngalagena_ka", 0x1B8B: "ngalagena_qa", 0x1B8C: "ngalagena_ga",
    0x1B8D: "ngalagena_nga", 0x1B8E: "ngalagena_ca", 0x1B8F: "ngalagena_ja",
    0x1B90: "ngalagena_za", 0x1B91: "ngalagena_nya", 0x1B92: "ngalagena_ta",
    0x1B93: "ngalagena_da", 0x1B94: "ngalagena_na", 0x1B95: "ngalagena_pa",
    0x1B96: "ngalagena_fa", 0x1B97: "ngalagena_va", 0x1B98: "ngalagena_ba",
    0x1B99: "ngalagena_ma", 0x1B9A: "ngalagena_ya", 0x1B9B: "ngalagena_ra",
    0x1B9C: "ngalagena_la", 0x1B9D: "ngalagena_wa", 0x1B9E: "ngalagena_sa",
    0x1B9F: "ngalagena_xa", 0x1BA0: "ngalagena_ha",
}
RARANGKEN = {
    0x1BA4: "rarangken_panghulu", 0x1BA5: "rarangken_panyuku",
    0x1BA6: "rarangken_paneleng", 0x1BA7: "rarangken_panolong",
    0x1BA8: "rarangken_pamepet", 0x1BA9: "rarangken_paneuleung",
    0x1B80: "rarangken_panyecek", 0x1B81: "rarangken_panglayar",
    0x1B82: "rarangken_pangwisad", 0x1BAA: "rarangken_pamaeh",
    0x1BA1: "rarangken_pamingkal", 0x1BA2: "rarangken_panyakra",
    0x1BA3: "rarangken_panyiku",
}
# Angka (digits 0-9): standalone glyphs, never carry rarangken marks, so
# they compose through make_syllable_generic() as a base with an always-
# empty mark list -- no separate rendering path needed, just recognition
# as a valid BASE entry (previously deliberately excluded: "part of the
# script but missing from our dataset" -- crops now exist for 1-9, 0 is
# still empty and is expected to fail at render time via load_random_crop).
ANGKA = {0x1BB0 + d: f"angka_{d}" for d in range(10)}
BASE = {**SWARA, **NGALAGENA, **ANGKA}

NO_LIGATURE_FEATURES = {f: False for f in
                         ["liga", "ccmp", "rlig", "clig", "rclt", "calt"]}


# --- syllable segmentation -------------------------------------------------

def segment_syllables(text):
    """Split Unicode Sundanese text into (base_cp, [mark_cp, ...]) tuples,
    with plain None entries for whitespace/punctuation/other characters
    (word/syllable breaks, quotes, hyphens, Latin punctuation used as an
    annotation convention in real transcriptions) passed through as layout
    separators.

    Only codepoints INSIDE the Sundanese Unicode block (U+1B80-1BBF) that
    we don't have a class for (kha, sya -- genuinely part of the script but
    missing from our dataset; angka/digits are now in BASE, though angka_0
    still has zero crops so rendering "0" fails at load_random_crop, not
    here) raise an error. Anything outside that block (Latin punctuation,
    ASCII digits, quotation marks) is always treated as a separator, never
    a hard failure -- it's not Aksara Sunda content to render, just
    transcription punctuation."""
    SUNDANESE_BLOCK = range(0x1B80, 0x1BC0)
    syllables = []
    i = 0
    n = len(text)
    while i < n:
        cp = ord(text[i])
        if cp in BASE:
            marks = []
            j = i + 1
            while j < n and ord(text[j]) in RARANGKEN:
                marks.append(ord(text[j]))
                j += 1
            syllables.append((cp, marks))
            i = j
        elif cp in SUNDANESE_BLOCK:
            raise ValueError(
                f"Karakter Aksara Sunda yang belum kita punya datanya pada indeks {i}: "
                f"{text[i]!r} (U+{cp:04X})")
        else:
            syllables.append((None, [text[i]]))
            i += 1
    return syllables


# --- GPOS offset measurement (generic, any base + any 0..N marks) ---------

_glyph_box_cache = {}


def _shape_boxes(text, disable_ligatures=False):
    key = (text, disable_ligatures)
    if key in _glyph_box_cache:
        return _glyph_box_cache[key]

    blob = hb.Blob.from_file_path(FONT_PATH)
    face = hb.Face(blob)
    font = hb.Font(face)
    upem = face.upem
    font.scale = (upem, upem)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, NO_LIGATURE_FEATURES if disable_ligatures else {})

    ft_face = freetype.Face(FONT_PATH)
    ft_face.set_pixel_sizes(0, 1000)
    factor = 1000 / upem
    pen_x = pen_y = 0
    boxes = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        ft_face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bmp = ft_face.glyph.bitmap
        left, top = ft_face.glyph.bitmap_left, ft_face.glyph.bitmap_top
        x = pen_x + pos.x_offset * factor + left
        y = pen_y - pos.y_offset * factor - top
        w, h = bmp.width, bmp.rows
        boxes.append({"gid": info.codepoint, "x": x, "y": y, "w": w, "h": h})
        pen_x += pos.x_advance * factor
        pen_y += pos.y_advance * factor

    _glyph_box_cache[key] = boxes
    return boxes


_offset_cache = {}


def get_mark_offsets(base_cp, mark_cps):
    """Returns a list of (dx_frac, dy_frac, scale) offsets, one per entry
    in mark_cps, relative to the base's ink box, measured from the font's
    real GPOS geometry (mark-to-mark included, ligature substitution
    disabled). Raises ValueError if the shaped output doesn't have exactly
    1 base + len(mark_cps) mark glyphs, rather than silently guessing."""
    if not mark_cps:
        return []
    key = (base_cp, tuple(mark_cps))
    if key in _offset_cache:
        return _offset_cache[key]

    base_only = _shape_boxes(chr(base_cp))
    if len(base_only) != 1:
        raise ValueError(f"Basis U+{base_cp:04X} tidak menghasilkan tepat 1 glyph sendirian.")
    base_gid = base_only[0]["gid"]

    text = chr(base_cp) + "".join(chr(c) for c in mark_cps)
    boxes = _shape_boxes(text, disable_ligatures=True)

    base_matches = [b for b in boxes if b["gid"] == base_gid]
    if len(base_matches) != 1:
        raise ValueError(
            f"Tidak bisa mengidentifikasi glyph basis U+{base_cp:04X} secara unik "
            f"dalam kombinasi {[hex(c) for c in mark_cps]} ({len(base_matches)} kecocokan).")
    base_box = base_matches[0]
    mark_boxes = [b for b in boxes if b is not base_box]

    if len(mark_boxes) != len(mark_cps):
        raise ValueError(
            f"U+{base_cp:04X} + {[hex(c) for c in mark_cps]}: font menghasilkan "
            f"{len(mark_boxes)} glyph tanda, bukan {len(mark_cps)} -- kemungkinan "
            f"ligatur belum sepenuhnya nonaktif untuk kombinasi ini, perlu verifikasi manual.")

    bx, by, bw, bh = base_box["x"], base_box["y"], base_box["w"], base_box["h"]
    bcx, bcy = bx + bw / 2, by + bh / 2
    offsets = []
    for mb in mark_boxes:
        mx, my, mw, mh = mb["x"], mb["y"], mb["w"], mb["h"]
        mcx, mcy = mx + mw / 2, my + mh / 2
        dx = (mcx - bcx) / bw
        dy = (mcy - bcy) / bh
        scale = mw / bw
        offsets.append((dx, dy, scale))

    _offset_cache[key] = offsets
    return offsets


# --- compositing ------------------------------------------------------------

def make_syllable_generic(base_cp, mark_cps):
    base_class = BASE[base_cp]
    base_img = load_random_crop(base_class)
    base_ink, _ = tight_ink(base_img)
    bw, bh = base_ink.size

    canvas_w = int(bw * (2.0 + 0.3 * len(mark_cps)))
    canvas_h = int(bh * (2.2 + 0.3 * len(mark_cps)))
    canvas = Image.new("L", (canvas_w, canvas_h), 255)
    bx = (canvas_w - bw) // 2
    by = (canvas_h - bh) // 2
    canvas.paste(base_ink, (bx, by))

    if mark_cps:
        import numpy as np
        base_arr = (np.array(base_ink) < 128).astype(np.uint8) * 255
        base_stroke = estimate_stroke_width(base_arr)
        offsets = get_mark_offsets(base_cp, mark_cps)
        for mark_cp, offset in zip(mark_cps, offsets):
            mark_class = RARANGKEN[mark_cp]
            jittered_offset, rotate_deg = _jitter_mark_placement(offset)
            canvas, bx, by = paste_mark(canvas, bx, by, bw, bh, base_stroke, mark_class,
                                         jittered_offset, rotate_deg=rotate_deg)

    tight, _ = tight_ink(canvas)
    scale_to_h = SYLLABLE_H / tight.height
    out_w = max(1, int(tight.width * scale_to_h))
    return tight.resize((out_w, SYLLABLE_H), Image.LANCZOS).point(lambda p: 0 if p < 180 else 255)


def syllable_label(base_cp, mark_cps):
    """The CTC ground-truth symbol for one syllable: its own Unicode
    substring (e.g. base+panyuku -> 'ᮊᮥ'), not an invented naming scheme --
    this makes the label vocabulary exactly the set of grapheme clusters
    that actually occur, with no separate mapping table to keep in sync."""
    return chr(base_cp) + "".join(chr(m) for m in mark_cps)


def render_text(text):
    """Render arbitrary Unicode Sundanese text (words separated by
    whitespace) into one composited PIL 'L' image, or (None, None) if the
    text has no renderable syllables.

    Returns (image, labels) where labels is a flat list of per-syllable
    grapheme-cluster strings (see syllable_label) with a single "<sp>"
    token inserted between words -- the CTC ground-truth sequence for the
    rendered image."""
    syllables = segment_syllables(text)

    words = []  # list of list-of-(image, label)
    current_word = []
    for base_cp, marks in syllables:
        if base_cp is None:
            if current_word:
                words.append(current_word)
                current_word = []
            continue
        img = make_syllable_generic(base_cp, marks)
        current_word.append((img, syllable_label(base_cp, marks)))
    if current_word:
        words.append(current_word)

    if not words:
        return None, None

    word_imgs = []
    labels = []
    for w_idx, syllables_in_word in enumerate(words):
        if w_idx > 0:
            labels.append("<sp>")
        syll_imgs = [im for im, _ in syllables_in_word]
        labels.extend(lbl for _, lbl in syllables_in_word)

        syll_gaps = [round(_jittered_gap(GAP_SYLLABLE, GAP_SYLLABLE_JITTER_FRAC))
                     for _ in range(len(syll_imgs) - 1)]
        total_w = sum(im.width for im in syll_imgs) + sum(syll_gaps)
        row = Image.new("L", (total_w, SYLLABLE_H), 255)
        x = 0
        for i, im in enumerate(syll_imgs):
            row.paste(im, (x, 0))
            x += im.width + (syll_gaps[i] if i < len(syll_gaps) else 0)
        word_imgs.append(row)

    word_gaps = [round(_jittered_gap(GAP_WORD, GAP_WORD_JITTER_FRAC))
                 for _ in range(len(word_imgs) - 1)]
    total_w = sum(im.width for im in word_imgs) + sum(word_gaps)
    sentence = Image.new("L", (total_w, SYLLABLE_H), 255)
    x = 0
    for i, im in enumerate(word_imgs):
        sentence.paste(im, (x, 0))
        x += im.width + (word_gaps[i] if i < len(word_gaps) else 0)

    # 5px white margin on all sides -- every syllable upstream is cropped
    # tight-to-ink (tight_ink, no margin), so without this the composited
    # sentence touches all four edges exactly. That flush framing is
    # inconsistent with how eval/inference images actually look, and gives
    # conv/pooling zero border context at the true content edges.
    pad = 5
    padded = Image.new("L", (total_w + 2 * pad, SYLLABLE_H + 2 * pad), 255)
    padded.paste(sentence, (pad, pad))
    return padded, labels


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "ᮊᮥᮙᮠ ᮓᮙᮀ"
    img, labels = render_text(text)
    out_path = os.path.join(ROOT, "_compositor_test.png")
    img.save(out_path)
    print("Rendered", len(text), "karakter,", len(labels), "label suku kata (lihat file untuk teksnya)")
    print("Saved to:", out_path)
