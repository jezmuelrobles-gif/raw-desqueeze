import numpy as np
import pytest

from desqueeze.color_science import (
    DEFAULT_LOG_EI_GAIN,
    apply_log_profile,
    detect_log_profile,
    log_encoding_slog2,
    log_encoding_slog3,
)


def test_slog3_middle_grey_matches_published_reference():
    # Sony's S-Log3 whitepaper: 18% grey (reflectance 0.18) encodes to
    # normalized code value ~0.4106 (10-bit code value ~420/1023).
    assert log_encoding_slog3(np.array([0.18]))[0] == pytest.approx(0.4105571, abs=1e-5)


def test_slog3_reference_white_above_middle_grey():
    grey = log_encoding_slog3(np.array([0.18]))[0]
    white = log_encoding_slog3(np.array([0.9]))[0]
    assert white > grey


def test_slog2_is_monotonic():
    x = np.linspace(0.001, 1.0, 50)
    y = log_encoding_slog2(x)
    assert np.all(np.diff(y) > 0)


def test_apply_log_profile_stays_in_16bit_range():
    image = np.random.randint(0, 65535, (20, 30, 3), dtype=np.uint16)
    out = apply_log_profile(image, "s-log3", DEFAULT_LOG_EI_GAIN)
    assert out.dtype == np.uint16
    assert out.shape == image.shape
    assert out.min() >= 0 and out.max() <= 65535


def test_apply_log_profile_rejects_unknown_profile():
    image = np.zeros((5, 5, 3), dtype=np.uint16)
    with pytest.raises(ValueError):
        apply_log_profile(image, "not-a-real-profile")


def test_detect_log_profile_on_synthetic_file_with_no_metadata(synthetic_raw):
    # The synthetic fixture has no Sony PictureProfile tag, so this should
    # return None rather than raising, whether or not exiftool is installed.
    assert detect_log_profile(synthetic_raw) is None
