"""CLI for the 'warm farm' creative batch grade -- an alternate, explicitly
non-neutral companion to `desqueeze` (see farm_grade.py for the rationale)."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from desqueeze.farm_pipeline import process_file_farm
from desqueeze.raw_io import find_raw_files


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--squeeze", type=float, default=1.33, show_default=True,
    help="Anamorphic squeeze factor to undo (new_width = width * squeeze).",
)
@click.option(
    "--out", "out_dir", type=click.Path(path_type=Path), default=Path("./farm_graded"),
    show_default=True, help="Output folder.",
)
@click.option("--recursive", is_flag=True, help="Recurse into subfolders when INPUT_PATH is a folder.")
@click.option("--overwrite", is_flag=True, help="Overwrite existing outputs instead of skipping them.")
@click.option(
    "--exposure-target", type=float, default=0.18, show_default=True,
    help="Target median scene-linear luminance every frame is normalized to "
         "before grading (18%% grey is the photographic default).",
)
def main(
    input_path: Path,
    squeeze: float,
    out_dir: Path,
    recursive: bool,
    overwrite: bool,
    exposure_target: float,
) -> None:
    """Batch-apply a warm 'farmhouse' creative grade to desqueezed RAW stills.

    INPUT_PATH is a single RAW file or a folder of RAW files. Unlike the main
    `desqueeze` command, this is deliberately NOT color-neutral: every frame is
    decoded with one fixed white-balance baseline and normalized to a common
    exposure target before a warm/rustic grade is applied, so the whole batch
    reads as one consistent look regardless of how each shot was actually lit
    or exposed.
    """
    if squeeze <= 0:
        raise click.BadParameter("--squeeze must be positive")

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
        result = process_file_farm(path, out_dir, squeeze, overwrite, exposure_target)

        if result.status == "success":
            succeeded += 1
            out = f"{result.output_size[0]}x{result.output_size[1]}" if result.output_size else "?"
            click.echo(f"OK    {path.name}  -> {out}")
        elif result.status == "skipped":
            skipped_existing += 1
            click.echo(f"SKIP  {path.name}  output already exists (use --overwrite)")
        else:
            failed += 1
            click.echo(f"FAIL  {path.name}  {result.error}", err=True)

    total_skipped = len(skipped) + skipped_existing
    click.echo("")
    click.echo(
        f"Processed {len(supported)}: {succeeded} succeeded, {failed} failed, "
        f"{total_skipped} skipped."
    )

    if failed:
        sys.exit(1)
