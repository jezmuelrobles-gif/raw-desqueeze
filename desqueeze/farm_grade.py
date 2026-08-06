"""Creative 'warm farmhouse' batch grade -- an alternate, explicitly
non-neutral companion to the main desqueeze pipeline's strict color-accuracy
goal (see color_science.py, which exists to *match the camera*; this module
exists to deliberately *not* match the camera).

Two concerns, handled separately:

1. "Perfectly exposed... homogeneous across all pictures": auto_expose_linear()
   normalizes each frame's exposure to a common target before grading, and the
   whole batch is decoded with one fixed white-balance baseline (see
   FIXED_DAYLIGHT_WB / raw_io.decode_raw(white_balance=...)) instead of each
   shot's own as-shot auto-WB estimate, which measurably drifts shot to shot
   across a real session (checked against this shoot's own RAW metadata).
   Without both of these, the same warm grade lands differently on every frame.

2. "Warm farm vibe": apply_farm_grade() implements a farmhouse/rustic film
   look researched from real preset breakdowns (warm push, matte shadow lift,
   gentle S-curve contrast with a soft highlight rolloff instead of a hard
   clip, muted overall saturation with selective vibrance, a sage-green shift,
   a barn-red warm boost, and a soft vignette) rather than an arbitrary guess.
"""

from __future__ import annotations

import cv2
import numpy as np

# Fixed daylight white balance -- a camera calibration constant (read from
# rawpy's raw.daylight_whitebalance), NOT a per-shot auto-WB estimate. Using
# this for every frame in the batch is what makes the "homogeneous" part work;
# passing use_camera_wb=True per-shot instead visibly drifted between frames
# shot in different light across this session.
FIXED_DAYLIGHT_WB = [2.4478163719177246, 0.9319279193878174, 1.2933659553527832, 0.0]


def auto_expose_linear(image: np.ndarray, target: float = 0.18, percentile: float = 50.0) -> np.ndarray:
    """Scale scene-linear `image` (uint16) so its median luminance hits `target`.

    Returns float64 in [0, 1]. This is independent of the creative grade --
    it's what makes "perfectly exposed" and "homogeneous" hold regardless of
    how bright or dark a given frame actually was.
    """
    img = image.astype(np.float64) / 65535.0
    luminance = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    current = np.percentile(luminance, percentile)
    if current <= 1e-6:
        return img
    # Log-profile RAWs are deliberately shot dark (exposed for highlight headroom,
    # pushed up in post/grading) -- this shoot's own median linear luminance ranges
    # from ~0.005 to ~0.26, so a large push (30x+) is normal here, not a rescue of a
    # mistake. The clamp exists only to stop a genuinely all-black/blown frame (e.g.
    # a lens-cap shot) from producing a nonsensical gain.
    gain = np.clip(target / current, 0.05, 50.0)
    return np.clip(img * gain, 0, 1)


def _apply_vignette(img: np.ndarray, strength: float) -> np.ndarray:
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = h / 2.0, w / 2.0
    max_r = np.sqrt(cx**2 + cy**2)
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max_r
    mask = np.clip(1 - strength * (r**2), 1 - strength, 1)
    return img * mask[..., None]


def apply_farm_grade(exposed_linear01: np.ndarray) -> np.ndarray:
    """Apply the warm farmhouse grade to exposure-normalized scene-linear data
    (float64, 0-1, from auto_expose_linear) and return a display-ready 16-bit
    sRGB image.
    """
    img = exposed_linear01.copy()

    # 1. Warm push while still in linear light: more red, less blue.
    img[..., 0] *= 1.10
    img[..., 2] *= 0.90
    img = np.clip(img, 0, 1)

    # 2. To display gamma -- contrast/hue moves from here on happen in a
    #    perceptual space, matching how real presets are actually built.
    img = np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(img, 1 / 2.4) - 0.055)
    img = np.clip(img, 0, 1)

    # 3. Matte shadow lift (film-style): raises the black floor without
    #    crushing the rest of the tonal range.
    black_lift = 0.06
    img = black_lift + (1 - black_lift) * img

    # 4. Gentle S-curve contrast, then a soft highlight rolloff (compress
    #    above a knee point instead of hard-clipping) so nothing blows out.
    contrast = 0.7
    img = np.clip(img + contrast * (img - 0.5) * img * (1 - img), 0, 1)
    knee = 0.80
    over = img > knee
    img[over] = knee + (img[over] - knee) / (1 + (img[over] - knee) * 2.5)
    img = np.clip(img, 0, 1)

    # 5. Hue/saturation pass: overall muted saturation with selective
    #    vibrance, a sage-green shift, and a barn-red warm boost.
    img8 = np.clip(img * 255, 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(img8, cv2.COLOR_RGB2HSV).astype(np.float64)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    green_mask = (h > 35) & (h < 85)
    red_mask = (h < 15) | (h > 165)

    h = h.copy()
    h[green_mask] = np.mod(h[green_mask] - 6, 180)  # sage: push toward yellow-green
    s[green_mask] *= 0.75  # ...and mute it
    s[red_mask] *= 1.15  # barn red: boost warm reds

    vibrance_boost = 1.0 + 0.20 * (1 - s / 255.0)  # lift muted colors more than already-bold ones
    s = np.clip(s * 0.90 * vibrance_boost, 0, 255)

    hsv_out = np.stack([h, s, v], axis=-1).astype(np.uint8)
    img8 = cv2.cvtColor(hsv_out, cv2.COLOR_HSV2RGB)
    img = img8.astype(np.float64) / 255.0

    # 6. Subtle vignette for a soft, hand-vignetted film feel.
    img = _apply_vignette(img, strength=0.15)

    return np.clip(img * 65535, 0, 65535).astype(np.uint16)
