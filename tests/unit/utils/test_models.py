"""Unit tests for ``FileCopyModel`` size/unit handling."""

import pytest

from pyntc.utils.models import FILE_SIZE_UNITS, FileCopyModel


def _model(**overrides):
    defaults = {
        "download_url": "http://example.com/image.bin",
        "checksum": "abc123",
        "file_name": "image.bin",
        "file_size": 1,
    }
    defaults.update(overrides)
    return FileCopyModel(**defaults)


def test_file_size_unit_defaults_to_bytes():
    model = _model(file_size=42)
    assert model.file_size_unit == "bytes"
    assert model.file_size_bytes == 42


@pytest.mark.parametrize(
    "unit, multiplier",
    [
        ("bytes", 1),
        ("megabytes", 1024**2),
        ("gigabytes", 1024**3),
    ],
)
def test_file_size_bytes_converts_from_unit(unit, multiplier):
    model = _model(file_size=3, file_size_unit=unit)
    assert model.file_size_bytes == 3 * multiplier
    assert model.file_size_bytes == 3 * FILE_SIZE_UNITS[unit]


def test_file_size_unit_is_normalised_to_lower_case():
    model = _model(file_size=5, file_size_unit="MegaBytes")
    assert model.file_size_unit == "megabytes"
    assert model.file_size_bytes == 5 * 1024**2


def test_unknown_file_size_unit_raises():
    with pytest.raises(ValueError, match="Unsupported file_size_unit"):
        _model(file_size=1, file_size_unit="terabytes")


def test_negative_file_size_raises():
    with pytest.raises(ValueError, match="non-negative"):
        _model(file_size=-1)


def test_file_size_is_optional():
    model = FileCopyModel(
        download_url="http://example.com/image.bin",
        checksum="abc123",
        file_name="image.bin",
    )
    assert model.file_size is None
    assert model.file_size_bytes is None
    # Unit default survives even when size is omitted.
    assert model.file_size_unit == "bytes"


def test_unknown_unit_raises_even_when_file_size_omitted():
    """``file_size_unit`` is always validated, whether ``file_size`` is set or not."""
    with pytest.raises(ValueError, match="Unsupported file_size_unit"):
        FileCopyModel(
            download_url="http://example.com/image.bin",
            checksum="abc123",
            file_name="image.bin",
            file_size_unit="terabytes",
        )


def test_file_size_unit_default_is_bytes_when_file_size_omitted():
    """Default unit survives and stays lowercase even with no ``file_size``."""
    model = FileCopyModel(
        download_url="http://example.com/image.bin",
        checksum="abc123",
        file_name="image.bin",
        file_size_unit="MegaBytes",
    )
    assert model.file_size_unit == "megabytes"
    assert model.file_size_bytes is None
