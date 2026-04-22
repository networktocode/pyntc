"""Shared helpers for integration tests that drive ``remote_file_copy``."""

import os
import posixpath

import pytest

from pyntc.utils.models import FileCopyModel

# Every protocol that ``remote_file_copy`` might transfer from. Individual device
# test modules can narrow this set when they only support a subset.
PROTOCOL_URL_VARS = {
    "ftp": "FTP_URL",
    "tftp": "TFTP_URL",
    "scp": "SCP_URL",
    "http": "HTTP_URL",
    "https": "HTTPS_URL",
    "sftp": "SFTP_URL",
}


def build_file_copy_model(url_env_var):
    """Build a ``FileCopyModel`` from a per-protocol URL env var.

    Reads ``FILE_HASH_ALGO`` and ``FILE_CHECKSUM`` from the environment.
    An autouse fixture in ``conftest.py`` sets both to the running test
    module's platform default before each module runs, so individual
    tests never have to hardcode an algorithm. Calls ``pytest.skip`` when
    any required env var is missing.
    """
    url = os.environ.get(url_env_var)
    checksum = os.environ.get("FILE_CHECKSUM")
    hashing_algorithm = os.environ.get("FILE_HASH_ALGO", "sha512")
    file_name = os.environ.get("FILE_NAME") or (posixpath.basename(url.split("?")[0]) if url else None)
    file_size = int(os.environ.get("FILE_SIZE", "0"))
    file_size_unit = os.environ.get("FILE_SIZE_UNIT", "bytes")

    if not all([url, checksum, file_name, file_size]):
        pytest.skip(f"{url_env_var} / FILE_CHECKSUM / FILE_SIZE environment variables not set")

    return FileCopyModel(
        download_url=url,
        checksum=checksum,
        file_name=file_name,
        file_size=file_size,
        file_size_unit=file_size_unit,
        hashing_algorithm=hashing_algorithm,
        timeout=900,
    )


def first_available_url(protocol_url_vars=None):
    """Return ``(scheme, url)`` for the first configured protocol URL.

    ``(None, None)`` when none of the env vars in ``protocol_url_vars`` are set.
    """
    for scheme, env_var in (protocol_url_vars or PROTOCOL_URL_VARS).items():
        url = os.environ.get(env_var)
        if url:
            return scheme, url
    return None, None
