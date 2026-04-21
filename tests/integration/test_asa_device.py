"""Integration tests for ASADevice.remote_file_copy.

These tests connect to an actual Cisco ASA device in the lab and are run manually.
They are NOT part of the CI unit test suite.

Usage (from project root):
    export ASA_HOST=<asa_ip>
    export ASA_USER=<user>
    export ASA_PASS=<pass>
    export ASA_SECRET=<enable_pass>
    export FTP_URL=ftp://<ftp_user>:<ftp_password>@<server_ip>/<file_name>
    export TFTP_URL=tftp://<server_ip>/<file_name>
    export SCP_URL=scp://<scp_user>:<scp_password>@<server_ip>:2222/<file_name>
    export HTTP_URL=http://<http_user>:<http_password>@<server_ip>:8081/<file_name>
    export HTTPS_URL=https://<https_user>:<https_password>@<server_ip>:8443/<file_name>
    export FILE_CHECKSUM=<sha512_hash>
    poetry run pytest tests/integration/test_asa_device.py -v

Set only the protocol URL vars for the servers you have available; each
protocol test will skip automatically if its URL is not set.

Environment variables:
    ASA_HOST        - IP address or hostname of the lab ASA
    ASA_USER        - SSH username
    ASA_PASS        - SSH password
    ASA_SECRET      - Enable password (can be same as ASA_PASS if not set)
    FTP_URL         - FTP URL of the file to transfer
    TFTP_URL        - TFTP URL of the file to transfer
    SCP_URL         - SCP URL of the file to transfer
    HTTP_URL        - HTTP URL of the file to transfer
    HTTPS_URL       - HTTPS URL of the file to transfer
    FILE_NAME       - Destination filename on the device (default: basename of URL path)
    FILE_CHECKSUM   - Expected sha512 checksum of the file (shared across all protocols)
"""

import os

import pytest

from pyntc.devices import ASADevice

from ._helpers import build_file_copy_model

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def device():
    """Connect to the lab ASA. Skips all tests if credentials are not set."""
    host = os.environ.get("ASA_HOST")
    user = os.environ.get("ASA_USER")
    password = os.environ.get("ASA_PASS")
    secret = os.environ.get("ASA_SECRET", password)

    if not all([host, user, password]):
        pytest.skip("ASA_HOST / ASA_USER / ASA_PASS environment variables not set")

    dev = ASADevice(host, user, password, secret=secret)
    yield dev
    dev.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_device_connects(device):
    """Verify the device is reachable and in enable mode."""
    assert device.is_active()


def test_check_file_exists_false(device, any_file_copy_model):
    """Before the copy, the file should not exist (or this test is a no-op if it does)."""
    result = device.check_file_exists(any_file_copy_model.file_name)
    # We just verify the method runs without error; state depends on lab environment
    assert isinstance(result, bool)


def test_get_remote_checksum_after_exists(device, any_file_copy_model):
    """If the file already exists, verify get_remote_checksum returns a non-empty string."""
    if not device.check_file_exists(any_file_copy_model.file_name):
        pytest.skip("File does not exist on device; run test_remote_file_copy_* first")
    checksum = device.get_remote_checksum(any_file_copy_model.file_name, hashing_algorithm="sha512")
    assert checksum and len(checksum) > 0


def test_remote_file_copy_ftp(device):
    """Transfer the file using FTP and verify it exists on the device."""
    model = build_file_copy_model("FTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_tftp(device):
    """Transfer the file using TFTP and verify it exists on the device."""
    model = build_file_copy_model("TFTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_scp(device):
    """Transfer the file using SCP and verify it exists on the device."""
    model = build_file_copy_model("SCP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_http(device):
    """Transfer the file using HTTP and verify it exists on the device."""
    model = build_file_copy_model("HTTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_https(device):
    """Transfer the file using HTTPS and verify it exists on the device."""
    model = build_file_copy_model("HTTPS_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_verify_file_after_copy(device, any_file_copy_model):
    """After a successful copy the file should verify cleanly."""
    if not device.check_file_exists(any_file_copy_model.file_name):
        pytest.skip("File does not exist on device; run a copy test first")
    assert device.verify_file(any_file_copy_model.checksum, any_file_copy_model.file_name, hashing_algorithm="sha512")
