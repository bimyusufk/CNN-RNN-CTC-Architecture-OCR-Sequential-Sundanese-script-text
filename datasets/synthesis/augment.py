# -*- coding: utf-8 -*-
"""Training-time augmentation for composited sentence images: small random
rotation, scale jitter, and elastic distortion (Simard et al. 2003 --
standard for handwriting/OCR augmentation). Applied on-the-fly per sample,
TRAIN split only -- val/test stay unaugmented so evaluation measures true
generalization, not augmentation-robustness.

Deliberately conservative ranges: this is text (not general imagery), so
excessive rotation/distortion can make a syllable genuinely unreadable /
mismatch its own label, which would corrupt training rather than help it.
"""
import math

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates


def elastic_distort(arr, alpha=6.0, sigma=4.0, rng=None, field_downscale=4):
    """arr: 2D numpy array (H, W), float or uint8. Random smooth
    displacement field, standard elastic-distortion augmentation.

    The displacement field is smooth by construction (gaussian_filter with
    sigma>=4px), so computing it at full resolution is wasted work -- our
    sentence images can be several thousand pixels wide, and gaussian_filter
    cost scales with pixel count (measured: ~0.5s/call at full res on a
    ~7M-pixel padded image, which would make on-the-fly per-sample training
    augmentation prohibitively slow, ~20 min/epoch). Instead the field is
    generated at 1/field_downscale resolution and upsampled -- the field
    itself is unaffected (still smooth, same statistics), only the
    per-pixel jitter from generating it at full res is lost, which the
    smoothing was discarding anyway."""
    rng = rng or np.random.default_rng()
    shape = arr.shape
    small_shape = (max(4, shape[0] // field_downscale), max(4, shape[1] // field_downscale))
    small_sigma = max(1.0, sigma / field_downscale)

    dx_small = (gaussian_filter((rng.random(small_shape) * 2 - 1), small_sigma, mode="constant", cval=0) * alpha).astype(np.float32)
    dy_small = (gaussian_filter((rng.random(small_shape) * 2 - 1), small_sigma, mode="constant", cval=0) * alpha).astype(np.float32)
    dx = np.array(Image.fromarray(dx_small, mode="F").resize((shape[1], shape[0]), Image.BILINEAR))
    dy = np.array(Image.fromarray(dy_small, mode="F").resize((shape[1], shape[0]), Image.BILINEAR))

    y, x = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    indices = (np.reshape(y + dy, (-1, 1)), np.reshape(x + dx, (-1, 1)))
    distorted = map_coordinates(arr, indices, order=1, mode="constant", cval=255).reshape(shape)
    return distorted


def augment_image(img_L, rng=None, max_rotate_deg=3.0, scale_range=(0.92, 1.08),
                   elastic_alpha=6.0, elastic_sigma=4.0, p_elastic=0.5):
    """img_L: PIL 'L' image (white=255 bg, black=0 ink). Returns a new PIL
    'L' image with rotation + scale jitter + (probabilistically) elastic
    distortion applied. Canvas is padded before transforms so ink is never
    clipped at the edges."""
    rng = rng or np.random.default_rng()

    # Rotation angle is capped per-image, not just globally, because a flat
    # degree range has a length-dependent pixel consequence: rotating pivots
    # around the center, so the far left/right ends of a WIDE line image
    # shift vertically by ~ (width/2)*sin(angle) -- for a long sentence
    # (width >> height) even 3 degrees can swing the ends by more than the
    # image's own height, which then roughly doubles the post-rotation tight
    # bbox height and (after the fixed-height=32 resize downstream) squashes
    # long sentences' effective per-character width far more than short
    # ones. Capping the induced half-height shift to a fixed fraction of the
    # image's own height keeps the *visual* rotation effect comparable
    # across sentence lengths instead of letting it blow up for long lines.
    max_vshift_frac = 0.15
    if img_L.width > img_L.height:
        max_shift_px = max_vshift_frac * img_L.height
        angle_cap = math.degrees(math.asin(min(1.0, max_shift_px / (img_L.width / 2))))
        eff_max_rotate = min(max_rotate_deg, angle_cap)
    else:
        eff_max_rotate = max_rotate_deg

    # Padding sized from the actual transform parameters, not a blanket
    # fraction of the larger dimension -- for a WIDE sentence image (our
    # images run into the thousands of px), "15% of max(W,H)" pads the
    # SHORT axis by an amount scaled to the LONG axis, producing a hugely
    # oversized working array (measured: 7M+ px) that made elastic
    # distortion far too slow for per-sample on-the-fly use. A small
    # rotation of a wide image needs height clearance ~W*sin(angle), and
    # width clearance ~H*sin(angle) -- each axis padded from the OTHER
    # axis's size, scaled by the actual (capped) max rotation, not a flat
    # 15%.
    rot_rad = math.radians(eff_max_rotate)
    max_scale = max(scale_range)
    pad_w = int(img_L.height * math.sin(rot_rad)) + int(img_L.width * (max_scale - 1)) + 15
    pad_h = int(img_L.width * math.sin(rot_rad)) + int(img_L.height * (max_scale - 1)) + 15
    padded = Image.new("L", (img_L.width + 2 * pad_w, img_L.height + 2 * pad_h), 255)
    padded.paste(img_L, (pad_w, pad_h))

    angle = rng.uniform(-eff_max_rotate, eff_max_rotate)
    rotated = padded.rotate(angle, resample=Image.BILINEAR, fillcolor=255, expand=False)

    scale = rng.uniform(*scale_range)
    new_size = (max(1, int(rotated.width * scale)), max(1, int(rotated.height * scale)))
    scaled = rotated.resize(new_size, Image.LANCZOS)

    if rng.random() < p_elastic:
        arr = np.array(scaled, dtype=np.float64)
        arr = elastic_distort(arr, alpha=elastic_alpha, sigma=elastic_sigma, rng=rng)
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        scaled = Image.fromarray(arr)

    # crop back to tight content + fixed small margin, so downstream
    # resize-to-height=32 behaves the same as for unaugmented images.
    # Threshold at 250 (not a bare 255-p) -- elastic distortion's
    # interpolation leaves faint near-white noise pixels (e.g. 254) far
    # from the real strokes, and a too-strict "not exactly 255" bbox check
    # was including that noise, massively inflating the crop.
    bbox = scaled.point(lambda p: 255 if p >= 250 else 0).point(lambda p: 255 - p).getbbox()
    if bbox is None:
        return img_L  # augmentation wiped it out (shouldn't happen with these ranges) -- fall back
    m = 6
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, x0 - m), max(0, y0 - m)
    x1, y1 = min(scaled.width, x1 + m), min(scaled.height, y1 + m)
    return scaled.crop((x0, y0, x1, y1))
