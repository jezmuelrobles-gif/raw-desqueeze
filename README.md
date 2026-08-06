# desqueeze

Batch CLI that takes RAW photo stills shot through a squeezed anamorphic lens
(default 1.33x) and outputs full-resolution, correctly desqueezed 16-bit TIFF
(and optionally linear DNG).

## How it works

1. Decode the RAW file with `rawpy`/LibRaw at full sensor resolution, 16-bit,
   as-shot white balance, standard demosaic -- no auto-exposure or creative
   color grading, so the output is a neutral base for editing in Lightroom,
   Resolve, or Photoshop. Embedded orientation is applied during decode.
   **If the source was shot with a Sony log picture profile** (S-Log2/S-Log3,
   auto-detected from the RAW's own metadata), the correct Sony log OETF is
   applied instead of a generic display gamma -- see "Log picture profiles"
   below for why this matters and isn't optional.
2. Stretch the image **horizontally only** by the squeeze factor
   (`new_width = original_width * squeeze`), using Lanczos resampling. Height
   is untouched, so no vertical resolution is thrown away.
3. Write 16-bit TIFF (and/or a best-effort linear DNG -- see limitation below).
4. Copy EXIF/IPTC/XMP metadata from the source RAW into the output via
   `exiftool`, and record the desqueeze in a custom `XMP-Desqueeze:*` tag
   (`Applied`, `SqueezeFactor`, `OriginalRawFile`).

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\pip install -e .
```

Metadata copying additionally requires **exiftool** on PATH (not
pip-installable -- it's a separate Perl-based tool):

```bash
winget install ExifTool
```

If exiftool isn't found, the tool still writes desqueezed image files -- it
just warns and skips metadata copy for that file rather than failing the
batch. Note exiftool is also used for log-profile detection (see "Log picture
profiles" below): without it, S-Log2/S-Log3 files silently fall back to the
normal gamma pipeline and will look flat/wrong compared to the camera.

## Usage

```bash
desqueeze <input_path_or_folder> [--squeeze 1.33] [--out ./desqueezed] [--format tiff,dng] [--recursive] [--overwrite]
```

- `INPUT_PATH` -- a single RAW file or a folder of RAW files.
- `--squeeze` -- squeeze factor to undo (default `1.33`).
- `--out` -- output folder (default `./desqueezed`).
- `--format` -- comma-separated: `tiff`, `dng`, or `tiff,dng` (default
  `tiff,dng` -- both are written unless you narrow it down). See the DNG
  limitation note below before relying on the DNG for anything color-critical.
- `--recursive` -- recurse into subfolders.
- `--overwrite` -- overwrite existing outputs (default: skip files whose
  output already exists).
- `--ei-gain` -- exposure gain applied before the log curve, for files shot in
  S-Log2/S-Log3 (default `2.25`, ignored for non-log files). See "Log picture
  profiles" below.

Supported input extensions: `.cr2` `.cr3` `.nef` `.nrw` `.arw` `.srf` `.sr2`
`.raf` `.rw2` `.orf` `.pef` `.dng` (auto-detected by extension; actual
decoding is handled by LibRaw, so this isn't tied to one camera brand).

Outputs are named `<original_filename>_desqueezed.tiff` /
`_desqueezed.dng`. Source RAW files are never modified or overwritten.

The tool prints per-file progress (`OK`/`SKIP`/`FAIL`, original -> output
dimensions) and a summary line, and exits non-zero if any file failed to
process (existing-output skips and unsupported-extension skips do not count
as failures).

### Example

```bash
desqueeze D:\Shoots\2026-08-04 --recursive --format tiff,dng --out D:\Shoots\2026-08-04\desqueezed
```

## Log picture profiles (S-Log2/S-Log3)

If a source RAW was shot with a Sony log picture profile, LibRaw's generic
demosaic + display gamma produces an image that looks nothing like what the
camera actually captured -- LibRaw has no concept of picture profiles, so it
applies its own standard tone curve regardless of what the camera embedded.
This isn't a cosmetic difference; it's the wrong transfer function entirely.

The tool detects this automatically (reading the RAW's own `Sony:PictureProfile`
tag via exiftool -- requires exiftool to be installed) and, when found, applies
the actual Sony S-Log2/S-Log3 opto-electronic transfer function instead,
[ported from the `colour-science` reference implementation](https://github.com/colour-science/colour/blob/develop/colour/models/rgb/transfer_functions/sony.py)
of Sony's published whitepapers. Files without a detected log profile use the
normal display-gamma pipeline described above -- this only kicks in for actual
log-profile shots, so it won't flatten ordinary photos.

The log OETF alone isn't enough to match the camera exactly: it also needs the
right exposure gain (how much the linear RAW data needs scaling before the log
curve places 18% grey/reference white correctly), since LibRaw's linear output
isn't calibrated to the camera's exposure-index convention for that profile.
The default (`--ei-gain 2.25`, roughly +1.17 stops) was calibrated by comparing
output against the camera's own embedded JPEG preview and corresponds closely
to Sony's documented guidance to overexpose S-Log3 by about a stop versus
standard metering. If a different camera/shoot doesn't match its own preview,
recalibrate by comparing against `rawpy`'s `extract_thumb()` output and
adjusting `--ei-gain` until the mean color/brightness lines up.

Known limitation: this reproduces Sony's exact **tone curve** (verified against
their published formula) but not their exact **color gamut** (S-Gamut3.Cine
matrix isn't public and isn't in LibRaw) -- so it's a close match, not a
bit-exact one. For final color-critical grading, treat the output the same way
you'd treat any RAW-converter rendering of log footage: as a strong starting
point, not the final word.

## DNG output limitation

True non-destructive DNG desqueeze (storing the stretch as a reversible
opcode DNG raw converters can undo) isn't feasible with the LibRaw-based
pipeline this tool uses -- LibRaw fully demosaics and develops the image
before the stretch is applied. `--format dng` instead writes a best-effort
**linear DNG** with the desqueeze baked directly into the pixel data: valid
DNG structure (DNG 1.4, `LinearRaw` photometric), but not reversible, and not
validated against Adobe's DNG SDK. **TIFF is the reliable, fully edit-ready
output** -- use DNG only if your downstream tool specifically requires a DNG
container, and verify it opens correctly there first.

## Edge cases handled

- Mixed RAW formats in the same batch.
- Files whose aspect ratio doesn't look like a squeezed anamorphic frame
  (roughly 1.15-1.65:1) print a warning but are desqueezed anyway rather than
  silently skipped.
- Corrupt/unreadable RAW files are logged and the batch continues.
- Files processed one at a time (not loaded all into memory at once), so
  large batches don't blow up memory.

## Testing

```bash
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest tests/ -v
```

Tests generate a minimal synthetic Bayer-CFA DNG on the fly (no binary
fixtures checked in) and verify: output width = input width * squeeze
(rounded), height unchanged; a circle squeezed by `1/squeeze` horizontally
reads back round after desqueezing (the classic anamorphic QC check);
batch/recursive/skip-on-corrupt-file behavior; and overwrite semantics.
