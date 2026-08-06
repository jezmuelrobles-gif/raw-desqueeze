"""Sony S-Log2/S-Log3 opto-electronic transfer functions and profile detection.

Why this exists: LibRaw/rawpy has no knowledge of Sony picture profiles. When a
RAW file was shot with a log picture profile (S-Log2/S-Log3), the camera's own
JPEG preview -- and the footage's whole downstream grading workflow -- expects
that flat log curve. LibRaw's generic demosaic + standard gamma produces a much
more contrasty/saturated image that doesn't match the source at all. This module
reproduces the correct curve so the desqueezed stills match what the camera
actually captured, instead of a generic RAW-converter look.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

# S-Log3 OETF, ported verbatim from colour-science (colour-science/colour,
# colour/models/rgb/transfer_functions/sony.py, log_encoding_SLog3), which in
# turn implements Sony's published "Technical Summary for S-Gamut3.Cine/S-Log3
# and S-Gamut3/S-Log3" whitepaper. x is scene-linear reflectance (0.18 == 18%
# grey card, 0.9 == reference white).
def log_encoding_slog3(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return np.where(
        x >= 0.01125000,
        (420 + np.log10((x + 0.01) / (0.18 + 0.01)) * 261.5) / 1023,
        (x * (171.2102946929 - 95) / 0.01125000 + 95) / 1023,
    )


# S-Log2 OETF, ported verbatim from colour-science (sony_slog.log_encoding_SLog2),
# implementing Sony's "S-Log White Paper". Included for PP7/PP8 variants that
# report as S-Log2 rather than S-Log3 (exact profile naming has varied by body).
def log_encoding_slog2(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return (4 * (16 + 219 * (0.616596 + 0.03 + 0.432699 * np.log10(0.037584 + x / 0.9)))) / 1023


# Linear-light exposure gain (and small black-level offset) applied before the
# log OETF: linear_effective = linear_raw * ei_gain + ei_offset. Compensates for
# rawpy's linear output not being calibrated to the camera's log-profile exposure
# reference. Calibrated by jointly fitting both parameters (scipy Nelder-Mead)
# against 10 of this camera's own embedded JPEG previews spanning the shoot's
# exposure range -- a single-parameter (gain-only) fit looked right on a bright
# reference shot but drifted noticeably on darker ones (shadows read brighter
# than the camera's own rendering); adding the offset term fixed that, dropping
# worst-case mean-RGB error from ~28/255 to ~2/255 across the sampled files.
# ei_gain ~2.29 corresponds to ~1.19 stops, consistent with Sony's documented
# guidance to overexpose S-Log3 by roughly a stop versus standard metering.
# Override via --ei-gain/--ei-offset if a different camera/shoot drifts.
DEFAULT_LOG_EI_GAIN = 2.2855
DEFAULT_LOG_EI_OFFSET = -0.00829


def apply_log_profile(
    linear_image: np.ndarray,
    profile: str,
    ei_gain: float = DEFAULT_LOG_EI_GAIN,
    ei_offset: float = DEFAULT_LOG_EI_OFFSET,
) -> np.ndarray:
    """Apply the appropriate Sony log OETF to a scene-linear (0-65535) image."""
    lin_norm = linear_image.astype(np.float64) / 65535.0
    scaled = np.clip(lin_norm * ei_gain + ei_offset, 0, None)
    if profile == "s-log3":
        encoded = log_encoding_slog3(scaled)
    elif profile == "s-log2":
        encoded = log_encoding_slog2(scaled)
    else:
        raise ValueError(f"unknown log profile: {profile}")
    return np.clip(encoded * 65535.0, 0, 65535).astype(np.uint16)


def detect_log_profile(source: Path) -> str | None:
    """Read the source RAW's Sony PictureProfile tag via exiftool and return
    "s-log3", "s-log2", or None (no log profile / exiftool unavailable / tag
    absent). Never raises -- detection failure just means "treat as normal".
    """
    if shutil.which("exiftool") is None:
        return None
    try:
        result = subprocess.run(
            ["exiftool", "-s3", "-Sony:PictureProfile", str(source)],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    value = result.stdout.strip().lower()
    if "s-log3" in value:
        return "s-log3"
    if "s-log2" in value:
        return "s-log2"
    return None
