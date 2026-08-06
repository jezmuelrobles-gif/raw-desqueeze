from pathlib import Path

import tifffile

from desqueeze.pipeline import process_file
from desqueeze.raw_io import find_raw_files, is_supported_raw


def test_is_supported_raw():
    assert is_supported_raw(Path("shot.CR3"))
    assert is_supported_raw(Path("shot.arw"))
    assert not is_supported_raw(Path("shot.jpg"))
    assert not is_supported_raw(Path("notes.txt"))


def test_find_raw_files_non_recursive_skips_subfolders(tmp_path):
    (tmp_path / "a.dng").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.dng").write_bytes(b"x")

    supported, skipped = find_raw_files(tmp_path, recursive=False)
    assert [p.name for p in supported] == ["a.dng"]
    assert [p.name for p in skipped] == ["notes.txt"]


def test_find_raw_files_recursive_includes_subfolders(tmp_path):
    (tmp_path / "a.dng").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.dng").write_bytes(b"x")

    supported, _ = find_raw_files(tmp_path, recursive=True)
    assert {p.name for p in supported} == {"a.dng", "b.dng"}


def test_process_file_end_to_end(synthetic_raw, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = process_file(
        synthetic_raw, out_dir, squeeze_factor=1.33, formats={"tiff"}, overwrite=False
    )

    assert result.status == "success"
    assert result.original_size == (1200, 800)
    assert result.output_size == (1596, 800)
    assert len(result.outputs) == 1

    tiff_path = result.outputs[0]
    assert tiff_path.name == "synthetic_source_desqueezed.tiff"
    img = tifffile.imread(str(tiff_path))
    assert img.shape == (800, 1596, 3)


def test_process_file_does_not_overwrite_by_default(synthetic_raw, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    first = process_file(synthetic_raw, out_dir, 1.33, {"tiff"}, overwrite=False)
    assert first.status == "success"

    second = process_file(synthetic_raw, out_dir, 1.33, {"tiff"}, overwrite=False)
    assert second.status == "skipped"

    third = process_file(synthetic_raw, out_dir, 1.33, {"tiff"}, overwrite=True)
    assert third.status == "success"


def test_process_file_reports_decode_failure_without_raising(tmp_path):
    bad_file = tmp_path / "corrupt.nef"
    bad_file.write_bytes(b"not a real raw file")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = process_file(bad_file, out_dir, 1.33, {"tiff"}, overwrite=False)

    assert result.status == "failed"
    assert result.error is not None
