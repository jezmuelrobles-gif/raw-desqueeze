import tifffile

from desqueeze.farm_pipeline import process_file_farm


def test_process_file_farm_end_to_end(synthetic_raw, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = process_file_farm(synthetic_raw, out_dir, squeeze_factor=1.33, overwrite=False)

    assert result.status == "success"
    assert result.output_size == (1596, 800)
    assert result.output.name == "synthetic_source_farm.tiff"

    img = tifffile.imread(str(result.output))
    assert img.shape == (800, 1596, 3)
    assert img.dtype.name == "uint16"


def test_process_file_farm_does_not_overwrite_by_default(synthetic_raw, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    first = process_file_farm(synthetic_raw, out_dir, 1.33, overwrite=False)
    assert first.status == "success"

    second = process_file_farm(synthetic_raw, out_dir, 1.33, overwrite=False)
    assert second.status == "skipped"

    third = process_file_farm(synthetic_raw, out_dir, 1.33, overwrite=True)
    assert third.status == "success"


def test_process_file_farm_reports_decode_failure_without_raising(tmp_path):
    bad_file = tmp_path / "corrupt.nef"
    bad_file.write_bytes(b"not a real raw file")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = process_file_farm(bad_file, out_dir, 1.33, overwrite=False)

    assert result.status == "failed"
    assert result.error is not None
