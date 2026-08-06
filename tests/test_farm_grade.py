import numpy as np
import pytest

from desqueeze.farm_grade import apply_farm_grade, auto_expose_linear


def test_auto_expose_hits_target_median():
    rng = np.random.default_rng(0)
    dark_image = (rng.random((50, 50, 3)) * 5000).astype(np.uint16)  # deliberately dark
    exposed = auto_expose_linear(dark_image, target=0.18)
    luminance = 0.2126 * exposed[..., 0] + 0.7152 * exposed[..., 1] + 0.0722 * exposed[..., 2]
    assert np.percentile(luminance, 50) == pytest.approx(0.18, abs=0.02)


def test_auto_expose_handles_all_black_image_without_crashing():
    black = np.zeros((10, 10, 3), dtype=np.uint16)
    out = auto_expose_linear(black)
    assert out.shape == black.shape
    assert np.all(out == 0)


def test_auto_expose_output_in_unit_range():
    rng = np.random.default_rng(1)
    image = (rng.random((20, 20, 3)) * 65535).astype(np.uint16)
    out = auto_expose_linear(image)
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_apply_farm_grade_produces_valid_16bit_output():
    rng = np.random.default_rng(2)
    exposed = rng.random((30, 40, 3))
    graded = apply_farm_grade(exposed)
    assert graded.dtype == np.uint16
    assert graded.shape == exposed.shape
    assert graded.min() >= 0 and graded.max() <= 65535


def test_farm_grade_lifts_shadows_off_pure_black():
    # The matte shadow lift should mean true black input never lands at 0 output.
    black = np.zeros((10, 10, 3))
    graded = apply_farm_grade(black)
    assert graded.mean() > 0
