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
    export FILE_SIZE=<image_size>
    export FILE_SIZE_UNIT=megabytes  # optional; defaults to "bytes"
    poetry run pytest tests/integration/test_eos_device.py -v

Set only the protocol URL vars for the servers you have available; each
protocol test will skip automatically if its URL is not set.

Environment variables:
    EOS_HOST         - IP address or hostname of the lab EOS device
    EOS_USER         - SSH / eAPI username
    EOS_PASS         - SSH / eAPI password
    FTP_URL          - FTP URL of the file to transfer
    TFTP_URL         - TFTP URL of the file to transfer
    SCP_URL          - SCP URL of the file to transfer
    HTTP_URL         - HTTP URL of the file to transfer
    HTTPS_URL        - HTTPS URL of the file to transfer
    SFTP_URL         - SFTP URL of the file to transfer
    FILE_NAME        - Destination filename on the device (default: basename of URL path)
    FILE_CHECKSUM    - Expected sha512 checksum of the file (shared across all protocols)
    FILE_SIZE        - Expected size of the file expressed in FILE_SIZE_UNIT units; used for
                       the pre-transfer free-space check
    FILE_SIZE_UNIT   - One of "bytes", "megabytes", or "gigabytes" (default: "bytes")
"""

import os
from unittest import mock

import pytest

from pyntc.devices import EOSDevice
from pyntc.errors import NotEnoughFreeSpaceError
from pyntc.utils.models import FILE_SIZE_UNITS, FileCopyModel

from ._helpers import PROTOCOL_URL_VARS, build_file_copy_model, first_available_url

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


def test_remote_file_copy_sftp(device):
    """Transfer the file using SFTP and verify it exists on the device."""
    model = build_file_copy_model("SFTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_verify_file_after_copy(device, any_file_copy_model):
    """After a successful copy the file should verify cleanly."""
    if not device.check_file_exists(any_file_copy_model.file_name):
        pytest.skip("File does not exist on device; run a copy test first")
    assert device.verify_file(any_file_copy_model.checksum, any_file_copy_model.file_name, hashing_algorithm="sha512")


# ---------------------------------------------------------------------------
# Free-space / pre-transfer tests (NAPPS-1091)
# ---------------------------------------------------------------------------


def test_get_free_space_returns_positive_int(device):
    """``_get_free_space`` parses the ``dir`` trailer into a positive int."""
    free = device._get_free_space()  # pylint: disable=protected-access
    assert isinstance(free, int)
    assert free > 0


def test_check_free_space_succeeds_for_small_request(device):
    """A 1-byte request must always fit; ``_check_free_space`` returns ``None``."""
    # pylint: disable=protected-access
    assert device._check_free_space(required_bytes=1) is None


def test_check_free_space_raises_when_required_exceeds_free(device):
    """When required bytes exceed what the device reports, raise NotEnoughFreeSpaceError."""
    # pylint: disable=protected-access
    free = device._get_free_space()
    with pytest.raises(NotEnoughFreeSpaceError):
        device._check_free_space(required_bytes=free + 1)


def test_file_size_unit_conversion_matches_device_free_space(device):
    """A megabyte-denominated request converts through ``FILE_SIZE_UNITS`` correctly."""
    # pylint: disable=protected-access
    free_bytes = device._get_free_space()
    one_mb = FILE_SIZE_UNITS["megabytes"]
    if free_bytes < one_mb:
        pytest.skip("Device has less than 1 MB free; conversion sanity test not meaningful")
    # 1 MB should always fit when free space is at least that large.
    assert device._check_free_space(required_bytes=one_mb) is None


def test_remote_file_copy_rejects_oversized_transfer(device):
    """remote_file_copy raises NotEnoughFreeSpaceError and never copies the file."""
    checksum = os.environ.get("FILE_CHECKSUM")
    scheme, url = first_available_url()
    if not (url and checksum):
        pytest.skip("No protocol URL / FILE_CHECKSUM environment variables not set")

    # pylint: disable=protected-access
    free_bytes = device._get_free_space()
    free_gb = free_bytes // FILE_SIZE_UNITS["gigabytes"]
    # Ask for ten times the currently-free capacity (minimum 10 GB), expressed in
    # gigabytes so this also exercises the unit conversion end-to-end.
    oversized_gb = max(free_gb * 10, 10)

    unique_name = f"pyntc_integration_space_check_{os.getpid()}_{scheme}.bin"
    model = FileCopyModel(
        download_url=url,
        checksum=checksum,
        file_name=unique_name,
        file_size=oversized_gb,
        file_size_unit="gigabytes",
        hashing_algorithm="sha512",
        timeout=60,
    )

    assert not device.check_file_exists(unique_name), "Unique filename unexpectedly exists before test"

    with pytest.raises(NotEnoughFreeSpaceError):
        device.remote_file_copy(model)

    # The transfer must never have started — file should still be absent.
    assert not device.check_file_exists(unique_name)


def test_remote_file_copy_accepts_declared_size_within_free_space(device):
    """A correctly-sized FileCopyModel copies without the space check interfering."""
    scheme, _url = first_available_url()
    if scheme is None:
        pytest.skip("No protocol URL environment variables set")
    model = build_file_copy_model(PROTOCOL_URL_VARS[scheme])
    # pylint: disable=protected-access
    free_bytes = device._get_free_space()
    assert model.file_size_bytes <= free_bytes, (
        "Configured FILE_SIZE/FILE_SIZE_UNIT exceeds device free space; update env vars"
    )
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_skips_space_check_when_file_size_omitted(device):
    """When FileCopyModel has no file_size, _check_free_space is never called.

    Spies on ``EOSDevice._check_free_space`` for the duration of the
    transfer and asserts it was not invoked. The transfer itself uses the
    same canonical ``FILE_NAME`` that the other copy tests use (the EOS
    copy command derives the source name from the destination filename
    when the URL has no path, so source and destination share a name).
    The file already existing from a prior test run is fine — the
    assertion that matters is ``spy.assert_not_called()`` combined with
    the transfer completing without raising ``FileTransferError``.
    """
    checksum = os.environ.get("FILE_CHECKSUM")
    file_name = os.environ.get("FILE_NAME")
    _, url = first_available_url()
    if not (url and checksum and file_name):
        pytest.skip("URL / FILE_CHECKSUM / FILE_NAME environment variables not set")

    model = FileCopyModel(
        download_url=url,
        checksum=checksum,
        file_name=file_name,
        hashing_algorithm="sha512",
        timeout=60,
    )  # file_size intentionally omitted
    assert model.file_size is None
    assert model.file_size_bytes is None

    with mock.patch.object(EOSDevice, "_check_free_space") as spy:
        device.remote_file_copy(model)

    spy.assert_not_called()
    assert device.check_file_exists(model.file_name)
