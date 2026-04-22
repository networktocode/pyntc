"""Shared fixtures for pyntc integration tests."""

import os
import posixpath

import pytest

from pyntc.utils.models import FileCopyModel

from ._helpers import PROTOCOL_URL_VARS


@pytest.fixture(scope="module")
def any_file_copy_model():
    """Return a ``FileCopyModel`` using the first available protocol URL.

    Used by tests that only need a file reference (existence checks, checksum
    verification) without caring about the transfer protocol. Skips if no
    protocol URL / ``FILE_CHECKSUM`` / ``FILE_SIZE`` env vars are set.
    """
    checksum = os.environ.get("FILE_CHECKSUM")
    file_size = int(os.environ.get("FILE_SIZE", "0"))
    file_size_unit = os.environ.get("FILE_SIZE_UNIT", "bytes")
    for env_var in PROTOCOL_URL_VARS.values():
        url = os.environ.get(env_var)
        if url and checksum and file_size:
            file_name = os.environ.get("FILE_NAME") or posixpath.basename(url.split("?")[0])
            return FileCopyModel(
                download_url=url,
                checksum=checksum,
                file_name=file_name,
                file_size=file_size,
                file_size_unit=file_size_unit,
                hashing_algorithm="sha512",
                timeout=900,
            )
    pytest.skip("No protocol URL / FILE_CHECKSUM / FILE_SIZE environment variables not set")
