"""Shared pytest fixtures: a minimal synthetic Bayer-CFA DNG, generated
on the fly (no binary fixture checked in) so LibRaw has something real to
decode in integration tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile


def _write_synthetic_dng(path: Path, width: int, height: int) -> None:
    bayer = np.full((height, width), 8000, dtype=np.uint16)

    r_mask = np.zeros_like(bayer, dtype=bool)
    r_mask[0::2, 0::2] = True
    b_mask = np.zeros_like(bayer, dtype=bool)
    b_mask[1::2, 1::2] = True
    bayer = bayer.astype(np.float64)
    bayer[b_mask] *= 0.9
    bayer = np.clip(bayer, 0, 65535).astype(np.uint16)

    # Datatype codes: 1=BYTE, 2=ASCII, 3=SHORT, 4=LONG, 5=RATIONAL
    extratags = [
        (254, 4, 1, (0,), True),  # NewSubfileType = 0 (main image)
        (271, 2, 0, "DesqueezeTest", True),  # Make
        (272, 2, 0, "SyntheticCam", True),  # Model
        (50706, 1, 4, (1, 4, 0, 0), True),  # DNGVersion
        (50707, 1, 4, (1, 1, 0, 0), True),  # DNGBackwardVersion
        (50708, 2, 0, "DesqueezeTestCam", True),  # UniqueCameraModel
        (33421, 3, 2, (2, 2), True),  # CFARepeatPatternDim
        (33422, 1, 4, (0, 1, 1, 2), True),  # CFAPattern: RGGB
        (50717, 4, 1, (65535,), True),  # WhiteLevel
        (50714, 4, 1, (0,), True),  # BlackLevel
        (50721, 5, 9, tuple(  # ColorMatrix1 (identity)
            v for pair in [(1, 1), (0, 1), (0, 1), (0, 1), (1, 1), (0, 1), (0, 1), (0, 1), (1, 1)]
            for v in pair
        ), True),
    ]

    tifffile.imwrite(
        str(path),
        bayer,
        photometric=tifffile.PHOTOMETRIC.CFA,
        planarconfig="contig",
        compression=None,
        extratags=extratags,
        shaped=False,
    )


@pytest.fixture
def synthetic_raw(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic_source.dng"
    _write_synthetic_dng(path, width=1200, height=800)
    return path
