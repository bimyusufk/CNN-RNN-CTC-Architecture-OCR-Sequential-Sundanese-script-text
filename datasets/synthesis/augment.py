# -*- coding: utf-8 -*-
"""Training-time augmentation for composited sentence images: small random
rotation, perspective skew, scale jitter, elastic distortion, page-curve
warp, and paper texture (Simard et al. 2003 for elastic distortion --
standard for handwriting/OCR augmentation; the rest simulate real-world
CAPTURE conditions -- a phone photo of a page/book, not a flatbed scan).
Applied on-the-fly per sample, TRAIN split only -- val/test stay
unaugmented so evaluation measures true generalization, not augmentation-
robustness.

Deliberately conservative ranges: this is text (not general imagery), so
excessive rotation/distortion can make a syllable genuinely unreadable /
mismatch its own label, which would corrupt training rather than help it.

Perspective and page-curve magnitudes are expressed as a fraction of the
image's own HEIGHT, not width -- same reasoning as the existing rotation
angle cap: our sentence images run into the thousands of px wide but stay
~32-260px tall, so a width-relative magnitude would blow up uncontrollably
for long sentences while staying invisible for short ones.

Fisheye/lens distortion was considered and deliberately NOT implemented:
true fisheye distortion is a wide-field-of-view effect visible across a
whole photographed PAGE. Our unit of augmentation is a single already-
cropped text LINE, at which scale literal fisheye math produces an
unrealistic bulge that doesn't correspond to what a line crop from a real
fisheye photo would actually look like. page_curve_distort() below is the
physically-grounded substitute: a page/book that isn't lying flat bows a
text line's baseline gently, which is a real and common capture artifact
at the single-line scale."""
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


def apply_perspective(img_L, rng, max_shift_frac=0.08, fillcolor=255):
    """Mild trapezoid/perspective skew -- simulates a camera not held
    perfectly perpendicular to the page (distinct from rotation, which
    simulates the page/camera being tilted in-plane). Each of the 4
    output corners' source mapping is jittered independently in y by up
    to max_shift_frac * height, producing a general mild quad warp rather
    than a single fixed trapezoid direction."""
    w, h = img_L.size
    max_shift = max_shift_frac * h
    dy_tl = rng.uniform(-max_shift, max_shift)
    dy_bl = rng.uniform(-max_shift, max_shift)
    dy_br = rng.uniform(-max_shift, max_shift)
    dy_tr = rng.uniform(-max_shift, max_shift)
    data = (
        0, dy_tl,
        0, h + dy_bl,
        w, h + dy_br,
        w, dy_tr,
    )
    return img_L.transform((w, h), Image.QUAD, data, resample=Image.BILINEAR, fillcolor=fillcolor)


def page_curve_distort(arr, rng, amplitude_frac=0.04):
    """Gentle single-hump vertical bow across the full width (zero
    displacement at both ends, max in the middle, random sign/magnitude)
    -- substitute for literal fisheye, see module docstring. Structurally
    like elastic_distort's map_coordinates warp, but a smooth deterministic
    sinusoid instead of filtered random noise: this is a low-frequency,
    whole-line effect (a page not lying flat), not per-pixel jitter."""
    h, w = arr.shape
    amplitude = amplitude_frac * h * rng.uniform(0.5, 1.0) * rng.choice([-1.0, 1.0])
    x = np.arange(w)
    dy_row = (amplitude * np.sin(np.pi * x / max(1, w))).astype(np.float32)
    dy = np.tile(dy_row, (h, 1))
    y, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    indices = (np.reshape(y + dy, (-1, 1)), np.reshape(xx.astype(np.float32), (-1, 1)))
    return map_coordinates(arr, indices, order=1, mode="constant", cval=255).reshape(arr.shape)


def add_paper_texture(img_L, rng, noise_std=5.0, gradient_strength=10.0):
    """Replace the pure-white (255) background with a subtle paper-like
    texture: a soft random-angle lighting gradient + fine grain noise.
    Applied LAST (after tight-cropping), on the final image -- adding it
    earlier would confuse the tight-crop bbox detection (which assumes a
    near-uniform white background) and would get partially undone by the
    later hard threshold in make_syllable_generic() if applied upstream
    of that. Clipped to [200, 255] so it always stays far below any ink
    threshold used elsewhere in this codebase (~<180) -- texture never
    risks being mistaken for a stroke."""
    arr = np.array(img_L, dtype=np.float32)
    h, w = arr.shape
    angle = rng.uniform(0, 2 * np.pi)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    grad = xx * np.cos(angle) + yy * np.sin(angle)
    span = grad.max() - grad.min()
    if span > 0:
        grad = (grad - grad.mean()) / span * gradient_strength
    else:
        grad = np.zeros_like(grad)
    noise = rng.normal(0, noise_std, size=(h, w))
    texture = np.clip(255 - np.abs(grad + noise), 200, 255).astype(np.float32)
    return Image.fromarray(np.minimum(arr, texture).astype(np.uint8))


def augment_image(img_L, rng=None, max_rotate_deg=3.0, scale_range=(0.92, 1.08),
                   elastic_alpha=6.0, elastic_sigma=4.0, p_elastic=0.5,
                   perspective_max_shift_frac=0.08, p_page_curve=0.35,
                   page_curve_amplitude_frac=0.04, p_paper_texture=1.0):
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
    # pad_h also needs clearance for perspective + page-curve, both
    # height-fraction-capped vertical displacements applied AFTER rotation/
    # scale below -- without this they'd get their own edges clipped by the
    # canvas rotation already sized.
    extra_vshift = (perspective_max_shift_frac + page_curve_amplitude_frac) * img_L.height
    pad_w = int(img_L.height * math.sin(rot_rad)) + int(img_L.width * (max_scale - 1)) + 15
    pad_h = (int(img_L.width * math.sin(rot_rad)) + int(img_L.height * (max_scale - 1))
              + int(extra_vshift) + 15)
    padded = Image.new("L", (img_L.width + 2 * pad_w, img_L.height + 2 * pad_h), 255)
    padded.paste(img_L, (pad_w, pad_h))

    angle = rng.uniform(-eff_max_rotate, eff_max_rotate)
    rotated = padded.rotate(angle, resample=Image.BILINEAR, fillcolor=255, expand=False)

    # Perspective skew -- unconditional, like rotation (both simulate
    # camera-angle variation, the baseline condition rather than a rare
    # event), applied on the already-padded canvas so its corner shifts
    # don't clip content.
    skewed = apply_perspective(rotated, rng, max_shift_frac=perspective_max_shift_frac)

    scale = rng.uniform(*scale_range)
    new_size = (max(1, int(skewed.width * scale)), max(1, int(skewed.height * scale)))
    scaled = skewed.resize(new_size, Image.LANCZOS)

    if rng.random() < p_elastic:
        arr = np.array(scaled, dtype=np.float64)
        arr = elastic_distort(arr, alpha=elastic_alpha, sigma=elastic_sigma, rng=rng)
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        scaled = Image.fromarray(arr)

    if rng.random() < p_page_curve:
        arr = np.array(scaled, dtype=np.float64)
        arr = page_curve_distort(arr, rng, amplitude_frac=page_curve_amplitude_frac)
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
    cropped = scaled.crop((x0, y0, x1, y1))

    if rng.random() < p_paper_texture:
        cropped = add_paper_texture(cropped, rng)

    return cropped
