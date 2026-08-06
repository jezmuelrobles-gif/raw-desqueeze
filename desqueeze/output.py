"""Output writers: 16-bit TIFF (reliable/edit-ready) and best-effort linear DNG."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

import numpy as np
import tifffile

# DNG 1.4 spec values.
_DNG_VERSION = (1, 4, 0, 0)
_DNG_BACKWARD_VERSION = (1, 4, 0, 0)

DNG_LIMITATION_NOTICE = (
    "DNG output bakes the desqueeze directly into the pixel data (LibRaw already "
    "demosaiced and developed the image before the stretch was applied). It is "
    "NOT a non-destructive raw edit and the squeeze cannot be undone from it. "
    "TIFF is the reliable, fully edit-ready output -- prefer it unless a DNG "
    "container is specifically required downstream, and verify DNG compatibility "
    "with your target raw converter before relying on it."
)

_REPLACE_RETRY_DELAYS = (0.5, 1.0, 2.0)  # seconds, for the final atomic swap into place


def _atomic_write(path: Path, write_fn: Callable[[str], None]) -> None:
    """Write via write_fn(temp_path) then atomically swap into `path`.

    Writing to a brand-new temp file (rather than truncating `path` in place)
    sidesteps a real, observed failure mode: Windows refuses to truncate a
    file that another process (commonly Explorer generating a thumbnail
    preview, or an antivirus/cloud-sync scan) has memory-mapped, which
    surfaces as `OSError: [Errno 22] Invalid argument`. The final rename is
    retried a few times since it can still transiently collide with the same
    kind of lock.
    """
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        write_fn(str(tmp_path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    last_exc: OSError | None = None
    for attempt, delay in enumerate((0.0, *_REPLACE_RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        try:
            os.replace(tmp_path, path)
            return
        except OSError as exc:
            last_exc = exc
    tmp_path.unlink(missing_ok=True)
    assert last_exc is not None
    raise last_exc


def write_tiff(image: np.ndarray, path: Path) -> None:
    """Write a 16-bit RGB TIFF, lossless-compressed."""

    def _write(tmp: str) -> None:
        tifffile.imwrite(
            tmp,
            image,
            photometric="rgb",
            planarconfig="contig",
            compression="zlib",
            shaped=False,
        )

    _atomic_write(path, _write)


def write_linear_dng(image: np.ndarray, path: Path, camera_model: str = "") -> None:
    """Write a best-effort Linear DNG with the desqueeze baked into the pixel data.

    See DNG_LIMITATION_NOTICE: this is a destructive fallback, not a true
    non-destructive raw desqueeze. Structure follows the DNG 1.4 spec closely
    enough to open in most DNG-aware raw converters, but isn't validated against
    Adobe's DNG SDK.
    """
    extratags = [
        (50706, "B", 4, _DNG_VERSION, True),  # DNGVersion
        (50707, "B", 4, _DNG_BACKWARD_VERSION, True),  # DNGBackwardVersion
        (50708, "s", 0, camera_model or "Unknown", True),  # UniqueCameraModel
    ]

    def _write(tmp: str) -> None:
        tifffile.imwrite(
            tmp,
            image,
            photometric=tifffile.PHOTOMETRIC.LINEAR_RAW,
            planarconfig="contig",
            extrasamples=False,
            compression="zlib",
            extratags=extratags,
            shaped=False,
        )

    _atomic_write(path, _write)
