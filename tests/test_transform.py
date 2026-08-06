import numpy as np
import pytest

from desqueeze.transform import (
    compute_output_width,
    desqueeze,
    unexpected_aspect_ratio_warning,
)


@pytest.mark.parametrize(
    ("width", "squeeze", "expected"),
    [
        (3000, 1.33, 3990),
        (4000, 1.33, 5320),
        (1920, 2.0, 3840),
        (1200, 1.0, 1200),
    ],
)
def test_compute_output_width(width, squeeze, expected):
    assert compute_output_width(width, squeeze) == expected


def test_desqueeze_stretches_width_only():
    image = np.zeros((800, 1200, 3), dtype=np.uint16)
    out = desqueeze(image, 1.33)
    assert out.shape == (800, 1596, 3)
    assert out.dtype == np.uint16


def test_desqueeze_identity_squeeze_preserves_dimensions():
    image = np.random.randint(0, 65535, (100, 150, 3), dtype=np.uint16)
    out = desqueeze(image, 1.0)
    assert out.shape == image.shape


def test_desqueeze_rejects_non_positive_squeeze():
    image = np.zeros((10, 10, 3), dtype=np.uint16)
    with pytest.raises(ValueError):
        desqueeze(image, 0)
    with pytest.raises(ValueError):
        desqueeze(image, -1.33)


def test_circle_qc_round_after_desqueeze():
    """The spec's QC check: a circle squeezed by 1/1.33 horizontally should
    read back round (equal bounding-box width/height) after desqueezing."""
    height, width = 800, 1200
    squeeze = 1.33
    cy, cx = height // 2, width // 2
    radius = 200
    yy, xx = np.mgrid[0:height, 0:width]
    squeezed_x_radius = radius / squeeze
    mask = (((xx - cx) / squeezed_x_radius) ** 2 + ((yy - cy) / radius) ** 2) <= 1.0

    image = np.zeros((height, width, 3), dtype=np.uint16)
    image[mask] = 65535

    out = desqueeze(image, squeeze)
    gray = out.mean(axis=2)
    ys, xs = np.where(gray > 32767)
    bbox_w = xs.max() - xs.min()
    bbox_h = ys.max() - ys.min()
    assert abs(bbox_w / bbox_h - 1.0) < 0.03


@pytest.mark.parametrize(
    ("width", "height"),
    [(3000, 2000), (4000, 3000), (1200, 800)],
)
def test_no_warning_for_typical_squeezed_ratios(width, height):
    assert unexpected_aspect_ratio_warning(width, height) is None


@pytest.mark.parametrize(
    ("width", "height"),
    [(1920, 1080), (4000, 2000)],
)
def test_warns_for_already_wide_ratios(width, height):
    warning = unexpected_aspect_ratio_warning(width, height)
    assert warning is not None
    assert "unusual" in warning
