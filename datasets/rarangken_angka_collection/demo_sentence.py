# -*- coding: utf-8 -*-
"""Demo: composite a simple real Sundanese sentence from ACTUAL collected
crops (real ngalagena/swara source images + real hand-drawn rarangken
samples), positioning each rarangken relative to its base ngalagena using
offsets measured from the font's own GPOS mark-attachment geometry (via
HarfBuzz) -- not guessed by hand.

Sentence: "Kumaha damang?" (How are you? / lit. "how [is your] health") --
an attested greeting, cross-checked against two independent sources
(detik.com and orami.co.id), both giving the identical Unicode string
"kumaha damang? (ᮊᮥᮙᮠ ᮓᮙᮀ?)" -- not a sentence composed from scratch.
  kumaha = ku (ka+panyuku/u) + ma (bare) + ha (bare)
  damang = da (bare) + mang (ma+panyecek/-ng koda)

Every syllable carries at most one rarangken (this also happens to sidestep
a real limitation found earlier: HarfBuzz shaping shows the font renders a
vowel-mark+koda-mark combination, e.g. "ring"=ra+i+ng, as a composed
ligature rather than two independently-stackable marks, so this from-scratch
compositor isn't yet verified for syllables needing two marks at once).

Usage: python datasets/rarangken_angka_collection/demo_sentence.py
"""
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from image_utils import crop_to_content, thin_stroke, thicken_stroke, estimate_stroke_width

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(os.path.dirname(ROOT), "aksara_sunda_full")

random.seed()

# (dx_frac, dy_frac, scale) measured via measure_offsets.py against "ka" --
# dx/dy are the mark-center offset from the base-ink-center, as a fraction
# of the base ink's own width/height; scale is the mark's width as a
# fraction of the base ink's width.
OFFSETS = {
    "panolong": (0.663, 0.251, 0.434),
    "panyuku": (-0.022, 0.711, 0.253),
    "panyecek": (-0.074, -0.751, 0.283),
}

SYLLABLE_H = 260
GAP_SYLLABLE = 6
GAP_WORD = 40


import contextlib

_active_pool = None  # None = unrestricted; else {class_name: [filenames]},
                      # set via crop_pool() below to confine which physical
                      # crop instances are drawable -- e.g. so a "test" split
                      # sentence can only be rendered from crop instances
                      # never used while rendering "train" split sentences.


@contextlib.contextmanager
def crop_pool(pool_dict):
    global _active_pool
    prev = _active_pool
    _active_pool = pool_dict
    try:
        yield
    finally:
        _active_pool = prev


def load_random_crop(class_name):
    d = os.path.join(DATASET_DIR, class_name)
    if _active_pool is not None and class_name in _active_pool:
        files = _active_pool[class_name]
    else:
        files = [f for f in os.listdir(d) if f.lower().endswith(".png")]
    f = random.choice(files)
    return Image.open(os.path.join(d, f)).convert("L")


def tight_ink(img_L):
    """Return (ink_only_image, bbox) cropped tight to content, no padding."""
    bbox = img_L.point(lambda p: 255 - p).getbbox()
    if bbox is None:
        return img_L, (0, 0, img_L.width, img_L.height)
    return img_L.crop(bbox), bbox


def paste_mark(canvas, bx, by, bw, bh, base_stroke, rarangken_class, offsets):
    """Paste one real rarangken crop onto `canvas`, positioned relative to
    the base ink's box (bx,by,bw,bh) using a measured (dx_frac, dy_frac,
    scale) offset, stroke-width-matched to base_stroke. Returns the
    (possibly grown) canvas. Shared by single- and two-mark syllables."""
    dx_frac, dy_frac, scale = offsets
    mark_img = load_random_crop(rarangken_class)
    mark_ink, _ = tight_ink(mark_img)
    mw, mh = mark_ink.size
    target_w = max(1, int(bw * scale))
    ratio = target_w / mw
    target_h = max(1, int(mh * ratio))

    # Stroke-match at the mark's NATIVE resolution, before downscaling --
    # not after. Marks often get resized down aggressively (e.g. to ~25%
    # width) to fit as a small attached symbol; running morphology (thin/
    # thicken) on an already-tiny binary image makes 1px of erosion/dilation
    # a huge relative change, and doing it on a hard-thresholded image
    # compounds into jagged/pixelated results. Predict the native stroke
    # width that will land on-target once resized by `ratio`, and correct
    # for that at full resolution where morphology is precise.
    mark_arr_native = (np.array(mark_ink) < 128).astype(np.uint8) * 255
    mark_stroke_native = estimate_stroke_width(mark_arr_native)
    if base_stroke > 0 and mark_stroke_native > 0 and ratio > 0:
        desired_native_stroke = base_stroke / ratio
        if mark_stroke_native > desired_native_stroke * 1.05:
            mark_ink = thin_stroke(mark_ink, target_factor=desired_native_stroke / mark_stroke_native)
        elif mark_stroke_native < desired_native_stroke * 0.95:
            mark_ink = thicken_stroke(mark_ink, target_factor=desired_native_stroke / mark_stroke_native)

    # Downscale AFTER stroke-matching, with LANCZOS antialiasing, and keep
    # it grayscale here (no hard threshold) -- binarizing is deferred to
    # the single final pass at the end of the whole syllable, so
    # antialiased edges survive instead of compounding jagged binary edges
    # across multiple resize steps.
    mark_resized = mark_ink.resize((target_w, target_h), Image.LANCZOS)

    base_cx, base_cy = bx + bw / 2, by + bh / 2
    mark_cx = base_cx + dx_frac * bw
    mark_cy = base_cy + dy_frac * bh
    px = int(mark_cx - target_w / 2)
    py = int(mark_cy - target_h / 2)

    canvas_w, canvas_h = canvas.size
    pad_l = max(0, -px)
    pad_t = max(0, -py)
    pad_r = max(0, (px + target_w) - canvas_w)
    pad_b = max(0, (py + target_h) - canvas_h)
    if pad_l or pad_t or pad_r or pad_b:
        new_canvas = Image.new("L", (canvas_w + pad_l + pad_r, canvas_h + pad_t + pad_b), 255)
        new_canvas.paste(canvas, (pad_l, pad_t))
        canvas = new_canvas
        px, py = px + pad_l, py + pad_t
        bx, by = bx + pad_l, by + pad_t

    mark_arr = np.array(mark_resized)
    canvas_arr = np.array(canvas)
    region = canvas_arr[py:py + target_h, px:px + target_w]
    canvas_arr[py:py + target_h, px:px + target_w] = np.minimum(region, mark_arr)
    return Image.fromarray(canvas_arr), bx, by


def make_syllable(base_class, rarangken_class=None):
    base_img = load_random_crop(base_class)
    base_ink, _ = tight_ink(base_img)
    bw, bh = base_ink.size

    canvas_w = int(bw * 2.0)
    canvas_h = int(bh * 2.2)
    canvas = Image.new("L", (canvas_w, canvas_h), 255)
    bx = (canvas_w - bw) // 2
    by = (canvas_h - bh) // 2
    canvas.paste(base_ink, (bx, by))

    if rarangken_class:
        base_arr = (np.array(base_ink) < 128).astype(np.uint8) * 255
        base_stroke = estimate_stroke_width(base_arr)
        offsets = OFFSETS[rarangken_class.replace("rarangken_", "")]
        canvas, bx, by = paste_mark(canvas, bx, by, bw, bh, base_stroke, rarangken_class, offsets)

    tight, _ = tight_ink(canvas)
    scale_to_h = SYLLABLE_H / tight.height
    out_w = max(1, int(tight.width * scale_to_h))
    return tight.resize((out_w, SYLLABLE_H), Image.LANCZOS).point(lambda p: 0 if p < 180 else 255)


def make_two_mark_syllable(base_class, rarangken1_class, offsets1, rarangken2_class, offsets2):
    """Same as make_syllable but pastes TWO real rarangken crops, using
    offsets measured from the font's own mark-to-mark GPOS positioning
    (with ligature GSUB substitution disabled) -- see measure_two_mark.py.
    Needed because two marks that both want the same zone (e.g. two
    "above" marks) get pushed apart from each other, not just from the
    base -- a naive independent-offset-per-mark placement would overlap
    them."""
    base_img = load_random_crop(base_class)
    base_ink, _ = tight_ink(base_img)
    bw, bh = base_ink.size

    canvas_w = int(bw * 2.4)
    canvas_h = int(bh * 2.6)
    canvas = Image.new("L", (canvas_w, canvas_h), 255)
    bx = (canvas_w - bw) // 2
    by = (canvas_h - bh) // 2
    canvas.paste(base_ink, (bx, by))

    base_arr = (np.array(base_ink) < 128).astype(np.uint8) * 255
    base_stroke = estimate_stroke_width(base_arr)

    canvas, bx, by = paste_mark(canvas, bx, by, bw, bh, base_stroke, rarangken1_class, offsets1)
    canvas, bx, by = paste_mark(canvas, bx, by, bw, bh, base_stroke, rarangken2_class, offsets2)

    tight, _ = tight_ink(canvas)
    scale_to_h = SYLLABLE_H / tight.height
    out_w = max(1, int(tight.width * scale_to_h))
    return tight.resize((out_w, SYLLABLE_H), Image.LANCZOS).point(lambda p: 0 if p < 180 else 255)


def make_word(syllables):
    imgs = [make_syllable(*s) for s in syllables]
    total_w = sum(im.width for im in imgs) + GAP_SYLLABLE * (len(imgs) - 1)
    canvas = Image.new("L", (total_w, SYLLABLE_H), 255)
    x = 0
    for im in imgs:
        canvas.paste(im, (x, 0))
        x += im.width + GAP_SYLLABLE
    return canvas


SENTENCE = [
    ("kumaha", [("ngalagena_ka", "rarangken_panyuku"), ("ngalagena_ma", None), ("ngalagena_ha", None)]),
    ("damang", [("ngalagena_da", None), ("ngalagena_ma", "rarangken_panyecek")]),
]
TRANSLITERATION = "kumaha damang?"
GLOSS = '"how are you?" -- lit. "how [is your] health"'


def load_caption_font(size, bold=False):
    candidates = (
        ["C:/Windows/Fonts/timesbd.ttf", "C:/Windows/Fonts/arialbd.ttf"] if bold else
        ["C:/Windows/Fonts/timesi.ttf", "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/arial.ttf"]
    )
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def main():
    words = [(label, make_word(syllables)) for label, syllables in SENTENCE]
    total_w = sum(im.width for _, im in words) + GAP_WORD * (len(words) - 1)
    sentence_img = Image.new("L", (total_w, SYLLABLE_H), 255)
    x = 0
    for label, im in words:
        sentence_img.paste(im, (x, 0))
        x += im.width + GAP_WORD

    margin = 40
    caption_h = 110
    canvas_w = sentence_img.width + 2 * margin
    canvas_h = sentence_img.height + 2 * margin + caption_h
    final = Image.new("L", (canvas_w, canvas_h), 255).convert("RGB")
    final.paste(sentence_img.convert("RGB"), (margin, margin))

    draw = ImageDraw.Draw(final)
    f_translit = load_caption_font(34, bold=True)
    f_gloss = load_caption_font(24)
    caption_y = margin + sentence_img.height + 20
    tb = draw.textbbox((0, 0), TRANSLITERATION, font=f_translit)
    draw.text(((canvas_w - (tb[2] - tb[0])) / 2, caption_y), TRANSLITERATION,
              font=f_translit, fill="black")
    gb = draw.textbbox((0, 0), GLOSS, font=f_gloss)
    draw.text(((canvas_w - (gb[2] - gb[0])) / 2, caption_y + 46), GLOSS,
              font=f_gloss, fill="#555555")

    out_path = os.path.join(ROOT, "_demo_sentence.png")
    final.save(out_path)
    print("Kalimat:", TRANSLITERATION)
    print("Disimpan ke:", out_path)


if __name__ == "__main__":
    main()
