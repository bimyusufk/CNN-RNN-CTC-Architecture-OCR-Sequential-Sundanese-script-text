# -*- coding: utf-8 -*-
"""Shared post-processing so every collected sample (hand-drawn or scanned)
ends up tightly cropped to its ink -- no dead-space margin -- which matters
for the word-synthesis step later: compositing characters that each carry a
large arbitrary margin would misplace their true glyph extent relative to
their neighbors.
"""
import cv2
import numpy as np
from PIL import Image

TARGET_FILL_PAD_FRAC = 0.35  # padding relative to ink size; ~59% fill, matching
                              # the reference swara/ngalagena data's 48-60% range


def crop_to_content(img_L, pad_frac=TARGET_FILL_PAD_FRAC, min_ink_px=3):
    """img_L: PIL 'L' mode image, white(255)=background, black(0)=ink.
    Returns a square white-padded crop tight around the ink, or None if the
    image is blank / the ink is too small to be a real stroke (noise)."""
    ink_mask = img_L.point(lambda p: 255 - p)
    bbox = ink_mask.getbbox()
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    bw, bh = x1 - x0, y1 - y0
    if bw < min_ink_px or bh < min_ink_px:
        return None

    side = max(bw, bh)
    pad = max(1, int(round(side * pad_frac)))
    side_padded = side + 2 * pad
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    left = int(round(cx - side_padded / 2.0))
    top = int(round(cy - side_padded / 2.0))

    canvas = Image.new("L", (side_padded, side_padded), 255)
    src_left, src_top = max(left, 0), max(top, 0)
    src_right = min(left + side_padded, img_L.width)
    src_bottom = min(top + side_padded, img_L.height)
    if src_right <= src_left or src_bottom <= src_top:
        return None
    region = img_L.crop((src_left, src_top, src_right, src_bottom))
    canvas.paste(region, (src_left - left, src_top - top))
    return canvas


def estimate_stroke_width(ink_mask_u8):
    """ink_mask_u8: numpy uint8, ink=255, background=0. Estimate the typical
    stroke width via distance transform (90th percentile of in-ink distance
    to the nearest edge, doubled) -- robust to thin stroke-end tapers that
    would drag a plain mean down."""
    dist = cv2.distanceTransform(ink_mask_u8, cv2.DIST_L2, 5)
    vals = dist[ink_mask_u8 > 0]
    if vals.size == 0:
        return 0.0
    return 2.0 * float(np.percentile(vals, 90))


def thin_stroke(img_L, target_factor=0.6):
    """img_L: PIL 'L' mode, white(255) bg / black(0) ink. Erodes the ink so
    its stroke width becomes approximately target_factor of its current
    width (e.g. 0.6 = 60% as thick). Returns img_L unchanged if there's no
    ink or the estimated width is already below target."""
    arr = np.array(img_L)
    ink = (arr < 128).astype(np.uint8) * 255
    if ink.sum() == 0:
        return img_L

    current_width = estimate_stroke_width(ink)
    if current_width <= 0:
        return img_L
    target_width = current_width * target_factor
    erode_each_side = (current_width - target_width) / 2.0
    k = int(round(erode_each_side))
    if k < 1:
        return img_L

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    eroded = cv2.erode(ink, kernel, iterations=1)
    if eroded.sum() == 0:  # over-eroded a very thin mark away entirely -- back off
        return img_L
    out = np.where(eroded > 0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def thicken_stroke(img_L, target_factor=1.3):
    """Inverse of thin_stroke: dilates the ink so its stroke width becomes
    approximately target_factor of its current width (e.g. 1.3 = 30%
    thicker). Returns img_L unchanged if there's no ink."""
    arr = np.array(img_L)
    ink = (arr < 128).astype(np.uint8) * 255
    if ink.sum() == 0:
        return img_L

    current_width = estimate_stroke_width(ink)
    if current_width <= 0:
        return img_L
    target_width = current_width * target_factor
    grow_each_side = (target_width - current_width) / 2.0
    k = int(round(grow_each_side))
    if k < 1:
        return img_L

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    dilated = cv2.dilate(ink, kernel, iterations=1)
    out = np.where(dilated > 0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def finalize_224(img_L, out_size=224, threshold=180):
    """crop_to_content -> resize -> re-binarize (resize blurs edges into
    gray, so threshold back to pure black/white). Returns None if blank."""
    cropped = crop_to_content(img_L)
    if cropped is None:
        return None
    resized = cropped.resize((out_size, out_size), Image.LANCZOS)
    return resized.point(lambda p: 0 if p < threshold else 255)
