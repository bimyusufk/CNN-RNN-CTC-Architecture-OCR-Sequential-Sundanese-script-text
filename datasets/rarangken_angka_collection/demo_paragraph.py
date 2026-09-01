# -*- coding: utf-8 -*-
"""Demo: composite a short Sundanese greeting-exchange PARAGRAPH from real
collected crops, with a transliteration caption below.

All five phrases are attested (not composed from scratch) -- cross-checked
against two independent sources (detik.com, orami.co.id), which give
identical Unicode strings for each:
    Sampurasun. Wilujeng sumping. Kumaha damang? Hatur nuhun. Sami-sami.
    ("Excuse me [greeting]. Welcome. How are you? Thank you. You're welcome.")

Decomposing every phrase into codepoints found THREE syllables that need two
rarangken at once (vowel + koda together): "jeng" (ja+pamepet+panyecek),
"ping" (pa+panghulu+panyecek), "tur" (ta+panyuku+panglayar). The font
collapses these to a single composed ligature glyph by default, which is
why an earlier version of this script fell back to rendering those three
via the font instead of real crops.

That fallback turned out to be avoidable: the font also carries proper
GPOS mark-to-mark rules as a fallback, they're just normally overridden by
the ligature (GSUB) substitution. Disabling liga/ccmp/rlig/clig/rclt/calt
in the HarfBuzz shaping call reveals the real 3-glyph positioning instead
of the 1-glyph ligature -- i.e. real geometry for where each of the two
marks sits, not a guess. That geometry (TWO_MARK_OFFSETS below) is applied
to real hand-drawn crops via make_two_mark_syllable(), so every syllable in
this paragraph -- all 29 -- is now composited from real character images,
none from font rendering.

Usage: python datasets/rarangken_angka_collection/demo_paragraph.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

from demo_sentence import (
    make_syllable, make_two_mark_syllable, OFFSETS,
    SYLLABLE_H, GAP_SYLLABLE, GAP_WORD, load_caption_font,
)

ROOT = os.path.dirname(os.path.abspath(__file__))

OFFSETS["pamaeh"] = (0.579, 0.359, 0.311)
OFFSETS["panghulu"] = (-0.071, -0.746, 0.294)

# Measured via measure_two_mark.py: shape base+mark1+mark2 with GSUB
# ligature features disabled, so HarfBuzz falls back to real GPOS
# mark-to-mark positioning (3 independent glyphs) instead of collapsing
# to one composed ligature glyph.
TWO_MARK_OFFSETS = {
    "jeng": [("rarangken_pamepet", (0.020, -0.740, 0.376)),
             ("rarangken_panyecek", (0.377, -0.751, 0.272))],
    "ping": [("rarangken_panghulu", (-0.068, -0.746, 0.294)),
              ("rarangken_panyecek", (0.260, -0.751, 0.284))],
    "tur": [("rarangken_panyuku", (0.040, 0.711, 0.233)),
             ("rarangken_panglayar", (0.021, -0.744, 0.375))],
}


def build_syllable(item):
    """item is (base_class, rarangken_class_or_None) for a one-mark real
    syllable, or ("TWO", base_class, key) for a two-mark real syllable."""
    if item[0] == "TWO":
        _, base_class, key = item
        (rk1, off1), (rk2, off2) = TWO_MARK_OFFSETS[key]
        return make_two_mark_syllable(base_class, rk1, off1, rk2, off2)
    return make_syllable(*item)


def build_word(syllable_items):
    imgs = [build_syllable(it) for it in syllable_items]
    total_w = sum(im.width for im in imgs) + GAP_SYLLABLE * (len(imgs) - 1)
    canvas = Image.new("L", (total_w, SYLLABLE_H), 255)
    x = 0
    for im in imgs:
        canvas.paste(im, (x, 0))
        x += im.width + GAP_SYLLABLE
    return canvas


# word -> list of syllables; each syllable is (base_ngalagena_class, rarangken_class_or_None)
# or ("FONT", key) for the three ligature-fallback syllables.
WORDS = {
    "sampurasun": [
        ("ngalagena_sa", None),
        ("ngalagena_ma", "rarangken_pamaeh"),
        ("ngalagena_pa", "rarangken_panyuku"),
        ("ngalagena_ra", None),
        ("ngalagena_sa", "rarangken_panyuku"),
        ("ngalagena_na", "rarangken_pamaeh"),
    ],
    "wilujeng": [
        ("ngalagena_wa", "rarangken_panghulu"),
        ("ngalagena_la", "rarangken_panyuku"),
        ("TWO", "ngalagena_ja", "jeng"),
    ],
    "sumping": [
        ("ngalagena_sa", "rarangken_panyuku"),
        ("ngalagena_ma", "rarangken_pamaeh"),
        ("TWO", "ngalagena_pa", "ping"),
    ],
    "kumaha": [
        ("ngalagena_ka", "rarangken_panyuku"),
        ("ngalagena_ma", None),
        ("ngalagena_ha", None),
    ],
    "damang": [
        ("ngalagena_da", None),
        ("ngalagena_ma", "rarangken_panyecek"),
    ],
    "hatur": [
        ("ngalagena_ha", None),
        ("TWO", "ngalagena_ta", "tur"),
    ],
    "nuhun": [
        ("ngalagena_na", "rarangken_panyuku"),
        ("ngalagena_ha", "rarangken_panyuku"),
        ("ngalagena_na", "rarangken_pamaeh"),
    ],
    "sami": [
        ("ngalagena_sa", None),
        ("ngalagena_ma", "rarangken_panghulu"),
    ],
}

SENTENCES = [
    ("Sampurasun.", ["sampurasun"]),
    ("Wilujeng sumping.", ["wilujeng", "sumping"]),
    ("Kumaha damang?", ["kumaha", "damang"]),
    ("Hatur nuhun.", ["hatur", "nuhun"]),
    ("Sami-sami.", ["sami", "sami"]),
]

TRANSLITERATION = "Sampurasun. Wilujeng sumping. Kumaha damang? Hatur nuhun. Sami-sami."
GLOSS = '"Excuse me. Welcome. How are you? Thank you. You\'re welcome."'
PROVENANCE = "seluruh 29 suku kata: crop asli tulisan tangan kami (termasuk jeng/ping/tur, ditempel dari 2 rarangken sekaligus)"


def main():
    line_gap = 30
    word_rows = []
    for label, word_names in SENTENCES:
        imgs = [build_word(WORDS[name]) for name in word_names]
        row_w = sum(im.width for im in imgs) + GAP_WORD * (len(imgs) - 1)
        row = Image.new("L", (row_w, SYLLABLE_H), 255)
        x = 0
        for im in imgs:
            row.paste(im, (x, 0))
            x += im.width + GAP_WORD
        word_rows.append(row)

    margin = 40
    caption_h = 150
    max_row_w = max(r.width for r in word_rows)
    total_h = sum(r.height for r in word_rows) + line_gap * (len(word_rows) - 1)
    canvas_w = max_row_w + 2 * margin
    canvas_h = total_h + 2 * margin + caption_h
    final = Image.new("RGB", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(final)

    y = margin
    for row in word_rows:
        x = margin
        final.paste(row.convert("RGB"), (x, y))
        y += row.height + line_gap

    f_translit = load_caption_font(28, bold=True)
    f_gloss = load_caption_font(20)
    f_prov = load_caption_font(15)
    caption_y = y + 10
    tb = draw.textbbox((0, 0), TRANSLITERATION, font=f_translit)
    draw.text(((canvas_w - (tb[2] - tb[0])) / 2, caption_y), TRANSLITERATION,
              font=f_translit, fill="black")
    gb = draw.textbbox((0, 0), GLOSS, font=f_gloss)
    draw.text(((canvas_w - (gb[2] - gb[0])) / 2, caption_y + 40), GLOSS,
              font=f_gloss, fill="#555555")
    pb = draw.textbbox((0, 0), PROVENANCE, font=f_prov)
    draw.text(((canvas_w - (pb[2] - pb[0])) / 2, caption_y + 76), PROVENANCE,
              font=f_prov, fill="#888888")

    out_path = os.path.join(ROOT, "_demo_paragraph.png")
    final.save(out_path)
    print("Paragraf:", TRANSLITERATION)
    print("Disimpan ke:", out_path)


if __name__ == "__main__":
    main()
