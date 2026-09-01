# -*- coding: utf-8 -*-
"""Shared HarfBuzz+FreeType glyph rendering for the rarangken/angka tools.

Naive font rendering (PIL's default layout) does not apply GPOS mark-to-base
positioning, so Sundanese combining marks land in the wrong place or overlap
the wrong glyph. Real text shaping (HarfBuzz) is required to render them
correctly -- see generate_worksheets.py and draw_collect.py for usage.
"""
import os

import numpy as np
import uharfbuzz as hb
import freetype
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(ROOT, "fonts", "NotoSansSundanese.ttf")

DOTTED_CIRCLE = "◌"


def shape_and_render(text, px_size=200, pad=20):
    blob = hb.Blob.from_file_path(FONT_PATH)
    face = hb.Face(blob)
    font = hb.Font(face)
    upem = face.upem
    font.scale = (upem, upem)

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf)

    ft_face = freetype.Face(FONT_PATH)
    ft_face.set_pixel_sizes(0, px_size)
    factor = px_size / upem

    pen_x = pen_y = 0
    glyphs = []
    min_x = min_y = 1e9
    max_x = max_y = -1e9
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        ft_face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bmp = ft_face.glyph.bitmap
        left, top = ft_face.glyph.bitmap_left, ft_face.glyph.bitmap_top
        x = pen_x + pos.x_offset * factor + left
        y = pen_y - pos.y_offset * factor - top
        w, h = bmp.width, bmp.rows
        arr = np.array(bmp.buffer, dtype=np.uint8).reshape(h, w) if w * h > 0 else np.zeros((0, 0), np.uint8)
        glyphs.append((x, y, arr))
        if w > 0 and h > 0:
            min_x, min_y = min(min_x, x), min(min_y, y)
            max_x, max_y = max(max_x, x + w), max(max_y, y + h)
        pen_x += pos.x_advance * factor
        pen_y += pos.y_advance * factor

    if min_x > max_x:
        min_x, min_y, max_x, max_y = 0, 0, px_size, px_size
    W, H = int(max_x - min_x) + 2 * pad, int(max_y - min_y) + 2 * pad
    canvas = np.zeros((H, W), np.uint8)
    for x, y, arr in glyphs:
        if arr.size == 0:
            continue
        ox, oy = int(x - min_x) + pad, int(y - min_y) + pad
        h, w = arr.shape
        x0, y0 = max(ox, 0), max(oy, 0)
        x1, y1 = min(ox + w, W), min(oy + h, H)
        if x1 <= x0 or y1 <= y0:
            continue
        sub = arr[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        canvas[y0:y1, x0:x1] = np.maximum(canvas[y0:y1, x0:x1], sub)
    return Image.fromarray(255 - canvas).convert("RGBA")
