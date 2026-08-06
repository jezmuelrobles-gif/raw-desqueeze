"""RAW file discovery and decoding via rawpy/LibRaw."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rawpy

# LibRaw auto-detects the actual codec from file content, so this list only
# gates which extensions we bother handing to it — not a hardcoded sensor/brand.
SUPPORTED_EXTENSIONS = {
    ".cr2", ".cr3",  # Canon
    ".nef", ".nrw",  # Nikon
    ".arw", ".srf", ".sr2",  # Sony
    ".raf",  # Fujifilm
    ".rw2",  # Panasonic
    ".orf",  # Olympus/OM System
    ".pef",  # Pentax
    ".dng",  # Adobe / generic
}


class RawDecodeError(RuntimeError):
    """Raised when a RAW file can't be read or decoded."""


@dataclass
class DecodedRaw:
    image: np.ndarray  # HxWx3 uint16, demosaiced, orientation already applied
    width: int
    height: int
    source_path: Path


def is_supported_raw(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def find_raw_files(root: Path, recursive: bool) -> tuple[list[Path], list[Path]]:
    """Return (supported, skipped) files under root (or [root] if it's a file)."""
    if root.is_file():
        return ([root], []) if is_supported_raw(root) else ([], [root])

    pattern = "**/*" if recursive else "*"
    candidates = sorted(p for p in root.glob(pattern) if p.is_file())
    supported = [p for p in candidates if is_supported_raw(p)]
    skipped = [p for p in candidates if not is_supported_raw(p)]
    return supported, skipped


def decode_raw(path: Path, linear: bool = False) -> DecodedRaw:
    """Decode a RAW file into a full-resolution, minimally-developed 16-bit RGB array.

    Development is intentionally neutral: as-shot white balance, standard demosaic,
    no auto-exposure/contrast/saturation adjustments. By default this also applies
    a standard display gamma, reproducing the same normal, recognizable rendering a
    RAW viewer or Lightroom's default develop would show. Pass linear=True to skip
    the gamma curve and get scene-linear data instead -- used when a Sony log
    picture profile (S-Log2/S-Log3) is detected, since the correct log OETF is
    applied afterward (see color_science.py) rather than a generic display gamma.

    Orientation embedded in the RAW is applied by LibRaw during postprocessing, so
    the returned array is already right-side-up.
    """
    try:
        with rawpy.imread(str(path)) as raw:
            kwargs = dict(
                use_camera_wb=True,
                no_auto_bright=True,
                output_bps=16,
                output_color=rawpy.ColorSpace.sRGB,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            )
            if linear:
                kwargs["gamma"] = (1, 1)
            rgb = raw.postprocess(**kwargs)
    except rawpy.LibRawError as exc:
        raise RawDecodeError(f"LibRaw failed to decode {path.name}: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise RawDecodeError(f"Could not read {path.name}: {exc}") from exc

    height, width = rgb.shape[:2]
    return DecodedRaw(image=rgb, width=width, height=height, source_path=path)
