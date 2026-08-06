"""Per-file processing pipeline: decode -> desqueeze -> write -> metadata copy."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from desqueeze.color_science import (
    DEFAULT_LOG_EI_GAIN,
    DEFAULT_LOG_EI_OFFSET,
    apply_log_profile,
    detect_log_profile,
)
from desqueeze.metadata import ExiftoolNotFoundError, MetadataCopyError, copy_metadata
from desqueeze.output import write_linear_dng, write_tiff
from desqueeze.raw_io import RawDecodeError, decode_raw
from desqueeze.transform import desqueeze, unexpected_aspect_ratio_warning


@dataclass
class FileResult:
    source: Path
    status: str  # "success", "skipped", or "failed"
    original_size: tuple[int, int] | None = None
    output_size: tuple[int, int] | None = None
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    log_profile: str | None = None


def process_file(
    source: Path,
    out_dir: Path,
    squeeze_factor: float,
    formats: set[str],
    overwrite: bool,
    log_ei_gain: float = DEFAULT_LOG_EI_GAIN,
    log_ei_offset: float = DEFAULT_LOG_EI_OFFSET,
) -> FileResult:
    """Run one RAW file through the full pipeline. Never raises -- failures are
    reported on the returned FileResult so a batch can continue past them.

    If the source RAW was shot with a Sony log picture profile (S-Log2/S-Log3,
    detected via its embedded metadata), the correct log OETF is applied so the
    output matches what the camera actually captured, instead of LibRaw's
    generic display gamma. See color_science.py for why this matters.
    """
    result = FileResult(source=source, status="failed")

    profile = detect_log_profile(source)
    result.log_profile = profile

    try:
        decoded = decode_raw(source, linear=(profile is not None))
    except RawDecodeError as exc:
        result.error = str(exc)
        return result

    if profile is not None:
        decoded.image = apply_log_profile(decoded.image, profile, log_ei_gain, log_ei_offset)

    result.original_size = (decoded.width, decoded.height)

    warning = unexpected_aspect_ratio_warning(decoded.width, decoded.height)
    if warning:
        result.warnings.append(warning)

    stretched = desqueeze(decoded.image, squeeze_factor)
    out_h, out_w = stretched.shape[:2]
    result.output_size = (out_w, out_h)

    stem = source.stem
    written: list[Path] = []

    if "tiff" in formats:
        tiff_path = out_dir / f"{stem}_desqueezed.tiff"
        if tiff_path.exists() and not overwrite:
            result.warnings.append(f"{tiff_path.name} already exists, skipped (use --overwrite)")
        else:
            try:
                write_tiff(stretched, tiff_path)
            except OSError as exc:
                result.error = f"failed writing {tiff_path.name}: {exc}"
                return result
            written.append(tiff_path)

    if "dng" in formats:
        dng_path = out_dir / f"{stem}_desqueezed.dng"
        if dng_path.exists() and not overwrite:
            result.warnings.append(f"{dng_path.name} already exists, skipped (use --overwrite)")
        else:
            try:
                write_linear_dng(stretched, dng_path)
            except OSError as exc:
                result.error = f"failed writing {dng_path.name}: {exc}"
                return result
            written.append(dng_path)

    if not written:
        result.status = "skipped"
        return result

    for path in written:
        try:
            copy_metadata(source, path, squeeze_factor, profile)
        except (ExiftoolNotFoundError, MetadataCopyError) as exc:
            result.warnings.append(str(exc))

    result.outputs = written
    result.status = "success"
    return result
