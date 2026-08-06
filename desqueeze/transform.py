"""The desqueeze transform itself: a horizontal-only Lanczos stretch."""

from __future__ import annotations

import cv2
import numpy as np

# Typical *native* (unsqueezed) still-photo aspect ratios: 4:3, 3:2, 16:9-ish.
# A squeezed anamorphic frame should sit close to this range before desqueezing;
# anything noticeably wider already looks like a normal/desqueezed photo, which
# is the signal worth surfacing to the user (per spec: warn, don't skip).
_EXPECTED_SQUEEZED_RATIO_RANGE = (1.15, 1.65)


def compute_output_width(width: int, squeeze_factor: float) -> int:
    return round(width * squeeze_factor)


def desqueeze(image: np.ndarray, squeeze_factor: float) -> np.ndarray:
    """Stretch `image` horizontally by `squeeze_factor` using Lanczos resampling.

    Height is left untouched (no vertical resolution is discarded, unlike a
    squash-the-height approach). Must be called on the full-resolution,
    already-demosaiced image, not a preview/thumbnail.
    """
    if squeeze_factor <= 0:
        raise ValueError(f"squeeze_factor must be positive, got {squeeze_factor}")

    height, width = image.shape[:2]
    new_width = compute_output_width(width, squeeze_factor)
    return cv2.resize(image, (new_width, height), interpolation=cv2.INTER_LANCZOS4)


def unexpected_aspect_ratio_warning(width: int, height: int) -> str | None:
    """Return a warning message if the source frame doesn't look like a squeezed
    anamorphic capture (i.e. it may already be a normal, non-anamorphic photo).

    This is a heuristic, not a hard rule — always applies the desqueeze regardless
    and lets the user judge the file from the warning.
    """
    ratio = width / height
    low, high = _EXPECTED_SQUEEZED_RATIO_RANGE
    if low <= ratio <= high:
        return None
    return (
        f"aspect ratio {width}x{height} ({ratio:.2f}:1) looks unusual for a "
        f"squeezed anamorphic frame (expected roughly {low:.2f}-{high:.2f}:1 "
        "before desqueeze) - this file may already be desqueezed or shot "
        "spherically. Desqueezing anyway."
    )
