"""Command-line interface for the anamorphic desqueeze batch tool."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from desqueeze.color_science import DEFAULT_LOG_EI_GAIN, DEFAULT_LOG_EI_OFFSET
from desqueeze.output import DNG_LIMITATION_NOTICE
from desqueeze.pipeline import process_file
from desqueeze.raw_io import find_raw_files

_VALID_FORMATS = {"tiff", "dng"}


def _parse_formats(ctx, param, value: str) -> set[str]:
    formats = {f.strip().lower() for f in value.split(",") if f.strip()}
    invalid = formats - _VALID_FORMATS
    if invalid:
        raise click.BadParameter(
            f"unsupported format(s): {', '.join(sorted(invalid))}. Choose from: tiff, dng."
        )
    if not formats:
        raise click.BadParameter("at least one format is required")
    return formats


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--squeeze", type=float, default=1.33, show_default=True,
    help="Anamorphic squeeze factor to undo (new_width = width * squeeze).",
)
@click.option(
    "--out", "out_dir", type=click.Path(path_type=Path), default=Path("./desqueezed"),
    show_default=True, help="Output folder.",
)
@click.option(
    "--format", "formats", default="tiff,dng", callback=_parse_formats,
    help="Comma-separated output formats: tiff,dng. Default: tiff,dng.",
)
@click.option("--recursive", is_flag=True, help="Recurse into subfolders when INPUT_PATH is a folder.")
@click.option("--overwrite", is_flag=True, help="Overwrite existing outputs instead of skipping them.")
@click.option(
    "--ei-gain", type=float, default=DEFAULT_LOG_EI_GAIN, show_default=True,
    help="Exposure gain applied before the log curve, for files shot in a Sony "
         "S-Log2/S-Log3 picture profile (auto-detected; ignored otherwise). "
         "Recalibrate if output doesn't match the camera's own JPEG preview.",
)
@click.option(
    "--ei-offset", type=float, default=DEFAULT_LOG_EI_OFFSET, show_default=True,
    help="Small black-level offset applied alongside --ei-gain before the log "
         "curve. Corrects shadow drift that a gain-only fit leaves behind.",
)
def main(
    input_path: Path,
    squeeze: float,
    out_dir: Path,
    formats: set[str],
    recursive: bool,
    overwrite: bool,
    ei_gain: float,
    ei_offset: float,
) -> None:
    """Batch-desqueeze anamorphic RAW photo stills into full-resolution TIFF/DNG.

    INPUT_PATH is a single RAW file or a folder of RAW files.
    """
    if squeeze <= 0:
        raise click.BadParameter("--squeeze must be positive")

    if "dng" in formats:
        click.echo(f"Note: {DNG_LIMITATION_NOTICE}", err=True)

    supported, skipped = find_raw_files(input_path, recursive)

    for path in skipped:
        click.echo(f"SKIP  {path} (unsupported extension)", err=True)

    if not supported:
        click.echo("No supported RAW files found.", err=True)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    succeeded = 0
    failed = 0
    skipped_existing = 0

    for path in supported:
        result = process_file(path, out_dir, squeeze, formats, overwrite, ei_gain, ei_offset)

        if result.status == "success":
            succeeded += 1
            orig = f"{result.original_size[0]}x{result.original_size[1]}" if result.original_size else "?"
            out = f"{result.output_size[0]}x{result.output_size[1]}" if result.output_size else "?"
            profile_note = f"  [{result.log_profile}]" if result.log_profile else ""
            click.echo(f"OK    {path.name}  {orig} -> {out}{profile_note}")
        elif result.status == "skipped":
            skipped_existing += 1
            click.echo(f"SKIP  {path.name}  all outputs already exist (use --overwrite)")
        else:
            failed += 1
            click.echo(f"FAIL  {path.name}  {result.error}", err=True)

        for warning in result.warnings:
            click.echo(f"WARN  {path.name}  {warning}", err=True)

    total_skipped = len(skipped) + skipped_existing
    click.echo("")
    click.echo(
        f"Processed {len(supported)}: {succeeded} succeeded, {failed} failed, "
        f"{total_skipped} skipped."
    )

    if failed:
        sys.exit(1)
