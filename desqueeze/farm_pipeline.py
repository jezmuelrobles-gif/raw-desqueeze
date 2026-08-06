"""Per-file pipeline for the 'warm farm' creative batch grade."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from desqueeze.farm_grade import FIXED_DAYLIGHT_WB, apply_farm_grade, auto_expose_linear
from desqueeze.output import write_tiff
from desqueeze.raw_io import RawDecodeError, decode_raw
from desqueeze.transform import desqueeze


@dataclass
class FarmFileResult:
    source: Path
    status: str  # "success", "skipped", or "failed"
    output_size: tuple[int, int] | None = None
    output: Path | None = None
    error: str | None = None


def process_file_farm(
    source: Path,
    out_dir: Path,
    squeeze_factor: float,
    overwrite: bool,
    exposure_target: float = 0.18,
) -> FarmFileResult:
    """Decode -> desqueeze -> normalize exposure -> warm farm grade -> write.

    Uses a fixed daylight white-balance baseline (not each shot's own as-shot
    estimate) and per-image exposure normalization so a whole batch reads as
    one consistent look regardless of how each frame was actually exposed.
    Never raises -- failures are reported on the returned result.
    """
    result = FarmFileResult(source=source, status="failed")

    out_path = out_dir / f"{source.stem}_farm.tiff"
    if out_path.exists() and not overwrite:
        result.status = "skipped"
        return result

    try:
        decoded = decode_raw(source, linear=True, white_balance=FIXED_DAYLIGHT_WB)
    except RawDecodeError as exc:
        result.error = str(exc)
        return result

    stretched = desqueeze(decoded.image, squeeze_factor)
    exposed = auto_expose_linear(stretched, target=exposure_target)
    graded = apply_farm_grade(exposed)

    out_h, out_w = graded.shape[:2]
    result.output_size = (out_w, out_h)

    try:
        write_tiff(graded, out_path)
    except OSError as exc:
        result.error = f"failed writing {out_path.name}: {exc}"
        return result

    result.output = out_path
    result.status = "success"
    return result
