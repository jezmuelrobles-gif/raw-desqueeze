"""EXIF/IPTC/XMP metadata propagation via the exiftool CLI.

exiftool is a separate, non-pip-installable dependency. Get it from
https://exiftool.org (Windows: the standalone .exe, renamed to exiftool.exe
and placed on PATH; or `winget install ExifTool`; or `choco install exiftool`).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "exiftool_desqueeze.config"

INSTALL_HINT = (
    "exiftool not found on PATH. Install it from https://exiftool.org "
    "(Windows: `winget install ExifTool`) to copy metadata into outputs. "
    "Continuing without metadata copy for this file."
)


class ExiftoolNotFoundError(RuntimeError):
    pass


class MetadataCopyError(RuntimeError):
    pass


def exiftool_available() -> bool:
    return shutil.which("exiftool") is not None


def copy_metadata(source: Path, dest: Path, squeeze_factor: float, log_profile: str | None = None) -> None:
    """Copy metadata from `source` into `dest` in place, and record the
    desqueeze in a custom XMP-Desqueeze:* tag (see exiftool_desqueeze.config).

    Deliberately excludes ExifImageWidth/ExifImageHeight (the source's
    pre-desqueeze dimensions would be stale) and resets Orientation to 1,
    since LibRaw already physically rotated the pixel data during decode --
    copying the source's Orientation flag as-is would cause viewers to
    rotate an already-upright image a second time.

    Raises ExiftoolNotFoundError if exiftool isn't installed, or
    MetadataCopyError if exiftool runs but reports failure.
    """
    if not exiftool_available():
        raise ExiftoolNotFoundError(INSTALL_HINT)

    if log_profile:
        color_note = (
            f"{log_profile.upper()} reconstructed from linear RAW (verified OETF, "
            "calibrated exposure gain) to match the camera's own picture profile rendering"
        )
    else:
        color_note = "sRGB, standard display gamma, as-shot white balance, no creative grading applied"

    cmd = [
        "exiftool",
        "-config", str(_CONFIG_PATH),
        "-TagsFromFile", str(source),
        "-all:all",
        "--EXIF:ExifImageWidth",
        "--EXIF:ExifImageHeight",
        "-Orientation#=1",  # '#' forces numeric mode -- plain "=1" silently writes 3 (Rotate 180)
        f"-XMP-Desqueeze:Applied=True",
        f"-XMP-Desqueeze:SqueezeFactor={squeeze_factor}",
        f"-XMP-Desqueeze:OriginalRawFile={source.name}",
        f"-XMP-Desqueeze:ColorSpace={color_note}",
        "-overwrite_original",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise MetadataCopyError(
            f"exiftool failed on {dest.name}: {result.stderr.strip() or result.stdout.strip()}"
        )
