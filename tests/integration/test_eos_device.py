"""Integration tests for EOSDevice.remote_file_copy.

These tests connect to an actual Arista EOS device in the lab and are run manually.
They are NOT part of the CI unit test suite.

Usage (from project root):
    export EOS_HOST=<eos_ip>
    export EOS_USER=<user>
    export EOS_PASS=<pass>
    export FTP_URL=ftp://<ftp_user>:<ftp_password>@<server_ip>/<file_name>
    export TFTP_URL=tftp://<server_ip>/<file_name>
    export SCP_URL=scp://<scp_user>:<scp_password>@<server_ip>/<file_name>
    export HTTP_URL=http://<http_user>:<http_password>@<server_ip>:8081/<file_name>
    export HTTPS_URL=https://<https_user>:<https_password>@<server_ip>:8443/<file_name>
    export SFTP_URL=sftp://<sftp_user>:<sftp_password>@<server_ip>/<file_name>
    export FILE_CHECKSUM=<sha512_hash>
    poetry run pytest tests/integration/test_eos_device.py -v

Set only the protocol URL vars for the servers you have available; each
protocol test will skip automatically if its URL is not set.

Environment variables:
    EOS_HOST        - IP address or hostname of the lab EOS device
    EOS_USER        - SSH / eAPI username
    EOS_PASS        - SSH / eAPI password
    FTP_URL         - FTP URL of the file to transfer
    TFTP_URL        - TFTP URL of the file to transfer
    SCP_URL         - SCP URL of the file to transfer
    HTTP_URL        - HTTP URL of the file to transfer
    HTTPS_URL       - HTTPS URL of the file to transfer
    SFTP_URL        - SFTP URL of the file to transfer
    FILE_NAME       - Destination filename on the device (default: basename of URL path)
    FILE_CHECKSUM   - Expected sha512 checksum of the file (shared across all protocols)
"""

import os
import posixpath

import pytest

from pyntc.devices import EOSDevice
from pyntc.utils.models import FileCopyModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROTOCOL_URL_VARS = {
    "ftp": "FTP_URL",
    "tftp": "TFTP_URL",
    "scp": "SCP_URL",
    "http": "HTTP_URL",
    "https": "HTTPS_URL",
    "sftp": "SFTP_URL",
}


def _make_model(url_env_var):
    """Build a FileCopyModel from a per-protocol URL env var.

    Calls pytest.skip if the URL or FILE_CHECKSUM is not set.
    """
    url = os.environ.get(url_env_var)
    checksum = os.environ.get("FILE_CHECKSUM")
    file_name = os.environ.get("FILE_NAME") or (posixpath.basename(url.split("?")[0]) if url else None)

    if not all([url, checksum, file_name]):
        pytest.skip(f"{url_env_var} / FILE_CHECKSUM environment variables not set")

    return FileCopyModel(
        download_url=url,
        checksum=checksum,
        file_name=file_name,
        hashing_algorithm="sha512",
        timeout=900,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def device():
    """Connect to the lab EOS device. Skips all tests if credentials are not set."""
    host = os.environ.get("EOS_HOST")
    user = os.environ.get("EOS_USER")
    password = os.environ.get("EOS_PASS")

    if not all([host, user, password]):
        pytest.skip("EOS_HOST / EOS_USER / EOS_PASS environment variables not set")

    dev = EOSDevice(host, user, password)
    yield dev
    dev.close()


@pytest.fixture(scope="module")
def any_file_copy_model():
    """Return a FileCopyModel using the first available protocol URL.

    Used by tests that only need a file reference (existence checks, checksum
    verification) without caring about the transfer protocol.  Skips if no
    protocol URL and FILE_CHECKSUM are set.
    """
    checksum = os.environ.get("FILE_CHECKSUM")
    for env_var in _PROTOCOL_URL_VARS.values():
        url = os.environ.get(env_var)
        if url and checksum:
            file_name = os.environ.get("FILE_NAME") or posixpath.basename(url.split("?")[0])
            return FileCopyModel(
                download_url=url,
                checksum=checksum,
                file_name=file_name,
                hashing_algorithm="sha512",
                timeout=900,
            )
    pytest.skip("No protocol URL / FILE_CHECKSUM environment variables not set")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_device_connects(device):
    """Verify the device is reachable and responds to show commands."""
    assert device.hostname
    assert device.os_version


def test_check_file_exists_false(device, any_file_copy_model):
    """Before the copy, the file should not exist (or this test is a no-op if it does)."""
    result = device.check_file_exists(any_file_copy_model.file_name)
    assert isinstance(result, bool)


def test_get_remote_checksum_after_exists(device, any_file_copy_model):
    """If the file already exists, verify get_remote_checksum returns a non-empty string."""
    if not device.check_file_exists(any_file_copy_model.file_name):
        pytest.skip("File does not exist on device; run test_remote_file_copy_* first")
    checksum = device.get_remote_checksum(any_file_copy_model.file_name, hashing_algorithm="sha512")
    assert checksum and len(checksum) > 0


def test_remote_file_copy_ftp(device):
    """Transfer the file using FTP and verify it exists on the device."""
    model = _make_model("FTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_tftp(device):
    """Transfer the file using TFTP and verify it exists on the device."""
    model = _make_model("TFTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_scp(device):
    """Transfer the file using SCP and verify it exists on the device."""
    model = _make_model("SCP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_http(device):
    """Transfer the file using HTTP and verify it exists on the device."""
    model = _make_model("HTTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_https(device):
    """Transfer the file using HTTPS and verify it exists on the device."""
    model = _make_model("HTTPS_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_sftp(device):
    """Transfer the file using SFTP and verify it exists on the device."""
    model = _make_model("SFTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_verify_file_after_copy(device, any_file_copy_model):
    """After a successful copy the file should verify cleanly."""
    if not device.check_file_exists(any_file_copy_model.file_name):
        pytest.skip("File does not exist on device; run a copy test first")
    assert device.verify_file(any_file_copy_model.checksum, any_file_copy_model.file_name, hashing_algorithm="sha512")
