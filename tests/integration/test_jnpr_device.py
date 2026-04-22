"""Integration tests for JunosDevice.remote_file_copy.

These tests connect to an actual Juniper Junos device in the lab and are run manually.
They are NOT part of the CI unit test suite.

Usage (from project root):
    export JUNOS_HOST=<junos_ip>
    export JUNOS_USER=<user>
    export JUNOS_PASS=<pass>
    export FTP_URL=ftp://<ftp_user>:<ftp_password>@<server_ip>/<file_name>
    export SCP_URL=scp://<scp_user>:<scp_password>@<server_ip>:2222/<file_name>
    export HTTP_URL=http://<http_user>:<http_password>@<server_ip>:8081/<file_name>
    export HTTPS_URL=https://<https_user>:<https_password>@<server_ip>:8443/<file_name>
    export FILE_CHECKSUM=<sha256_hash>
    export FILE_SIZE=<image_size>
    export FILE_SIZE_UNIT=megabytes  # optional; defaults to "bytes"
    poetry run pytest tests/integration/test_jnpr_device.py -v

Set only the protocol URL vars for the servers you have available; each
protocol test will skip automatically if its URL is not set.

Environment variables:
    JUNOS_HOST       - IP address or hostname of the lab Junos device
    JUNOS_USER       - NETCONF / SSH username
    JUNOS_PASS       - NETCONF / SSH password
    FTP_URL          - FTP URL of the file to transfer
    SCP_URL          - SCP URL of the file to transfer
    HTTP_URL         - HTTP URL of the file to transfer
    HTTPS_URL        - HTTPS URL of the file to transfer
    FILE_NAME        - Destination filename on the device (default: basename of URL path)
    FILE_CHECKSUM    - Expected sha256 checksum of the file (Junos does not implement sha512;
                       the hashing algorithm is pinned to sha256 via ``JUNOS_INTEGRATION_HASH_ALGO``
                       at module level — edit that constant for md5 / sha1 labs)
    FILE_SIZE        - Expected size of the file expressed in FILE_SIZE_UNIT units; used for
                       the pre-transfer free-space check
    FILE_SIZE_UNIT   - One of "bytes", "megabytes", or "gigabytes" (default: "bytes")
"""

import os
from unittest import mock

import pytest

from pyntc.devices import JunosDevice
from pyntc.errors import NotEnoughFreeSpaceError
from pyntc.utils.models import FILE_SIZE_UNITS, FileCopyModel

from ._helpers import PROTOCOL_URL_VARS, build_file_copy_model, first_available_url

# Junos ``fs.cp`` does not accept TFTP URLs, so narrow the protocol set before
# any protocol-aware fixture/test reads from it.
JUNOS_PROTOCOL_URL_VARS = {scheme: env_var for scheme, env_var in PROTOCOL_URL_VARS.items() if scheme != "tftp"}

# Junos ``file checksum`` RPC does not implement sha512. The integration run is
# pinned to sha256; labs that ship ``md5`` / ``sha1`` binaries edit this constant
# and regenerate ``FILE_CHECKSUM`` accordingly.
JUNOS_INTEGRATION_HASH_ALGO = "sha256"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def device():
    """Connect to the lab Junos device. Skips all tests if credentials are not set."""
    host = os.environ.get("JUNOS_HOST")
    user = os.environ.get("JUNOS_USER")
    password = os.environ.get("JUNOS_PASS")

    if not all([host, user, password]):
        pytest.skip("JUNOS_HOST / JUNOS_USER / JUNOS_PASS environment variables not set")

    dev = JunosDevice(host, user, password)
    yield dev
    dev.close()


def _junos_dest(file_name):
    """Return the absolute destination path on Junos for ``file_name``."""
    return f"/var/tmp/{file_name}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_device_connects(device):
    """Verify the device is reachable and responds to facts queries."""
    assert device.hostname
    assert device.os_version


def test_check_file_exists_false(device, any_file_copy_model):
    """Before the copy, the file should not exist (or this test is a no-op if it does)."""
    result = device.check_file_exists(_junos_dest(any_file_copy_model.file_name))
    assert isinstance(result, bool)


def test_remote_file_copy_ftp(device):
    """Transfer the file using FTP and verify it exists on the device."""
    model = build_file_copy_model("FTP_URL", hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO)
    dest = _junos_dest(model.file_name)
    device.remote_file_copy(model, dest=dest)
    assert device.check_file_exists(dest)


def test_remote_file_copy_scp(device):
    """Transfer the file using SCP and verify it exists on the device."""
    model = build_file_copy_model("SCP_URL", hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO)
    dest = _junos_dest(model.file_name)
    device.remote_file_copy(model, dest=dest)
    assert device.check_file_exists(dest)


def test_remote_file_copy_http(device):
    """Transfer the file using HTTP and verify it exists on the device."""
    model = build_file_copy_model("HTTP_URL", hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO)
    dest = _junos_dest(model.file_name)
    device.remote_file_copy(model, dest=dest)
    assert device.check_file_exists(dest)


def test_remote_file_copy_https(device):
    """Transfer the file using HTTPS and verify it exists on the device."""
    model = build_file_copy_model("HTTPS_URL", hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO)
    dest = _junos_dest(model.file_name)
    device.remote_file_copy(model, dest=dest)
    assert device.check_file_exists(dest)


def test_verify_file_after_copy(device, any_file_copy_model):
    """After a successful copy the file should verify cleanly."""
    dest = _junos_dest(any_file_copy_model.file_name)
    if not device.check_file_exists(dest):
        pytest.skip("File does not exist on device; run a copy test first")
    assert device.verify_file(any_file_copy_model.checksum, dest, hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO)


# ---------------------------------------------------------------------------
# Free-space / pre-transfer tests (NAPPS-1085)
# ---------------------------------------------------------------------------


def test_get_free_space_returns_positive_int(device):
    """``_get_free_space`` returns a positive int parsed from storage_usage."""
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
    assert device._check_free_space(required_bytes=one_mb) is None


def test_remote_file_copy_rejects_oversized_transfer(device):
    """remote_file_copy raises NotEnoughFreeSpaceError and never copies the file."""
    checksum = os.environ.get("FILE_CHECKSUM")
    scheme, url = first_available_url(JUNOS_PROTOCOL_URL_VARS)
    if not (url and checksum):
        pytest.skip("No protocol URL / FILE_CHECKSUM environment variables set")

    # pylint: disable=protected-access
    free_bytes = device._get_free_space()
    free_gb = free_bytes // FILE_SIZE_UNITS["gigabytes"]
    oversized_gb = max(free_gb * 10, 10)

    unique_name = f"pyntc_integration_space_check_{os.getpid()}_{scheme}.bin"
    dest = _junos_dest(unique_name)
    model = FileCopyModel(
        download_url=url,
        checksum=checksum,
        file_name=unique_name,
        file_size=oversized_gb,
        file_size_unit="gigabytes",
        hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO,
        timeout=60,
    )

    assert not device.check_file_exists(dest), "Unique filename unexpectedly exists before test"

    with pytest.raises(NotEnoughFreeSpaceError):
        device.remote_file_copy(model, dest=dest)

    assert not device.check_file_exists(dest)


def test_remote_file_copy_accepts_declared_size_within_free_space(device):
    """A correctly-sized FileCopyModel copies without the space check interfering."""
    scheme, _url = first_available_url(JUNOS_PROTOCOL_URL_VARS)
    if scheme is None:
        pytest.skip("No protocol URL environment variables set")
    model = build_file_copy_model(JUNOS_PROTOCOL_URL_VARS[scheme], hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO)
    # pylint: disable=protected-access
    free_bytes = device._get_free_space()
    assert model.file_size_bytes <= free_bytes, (
        "Configured FILE_SIZE/FILE_SIZE_UNIT exceeds device free space; update env vars"
    )
    dest = _junos_dest(model.file_name)
    device.remote_file_copy(model, dest=dest)
    assert device.check_file_exists(dest)


def test_remote_file_copy_skips_space_check_when_file_size_omitted(device):
    """When FileCopyModel has no file_size, _check_free_space is never called."""
    checksum = os.environ.get("FILE_CHECKSUM")
    file_name = os.environ.get("FILE_NAME")
    _, url = first_available_url(JUNOS_PROTOCOL_URL_VARS)
    if not (url and checksum and file_name):
        pytest.skip("URL / FILE_CHECKSUM / FILE_NAME environment variables not set")

    model = FileCopyModel(
        download_url=url,
        checksum=checksum,
        file_name=file_name,
        hashing_algorithm=JUNOS_INTEGRATION_HASH_ALGO,
        timeout=60,
    )  # file_size intentionally omitted
    assert model.file_size is None
    assert model.file_size_bytes is None

    dest = _junos_dest(file_name)
    with mock.patch.object(JunosDevice, "_check_free_space") as spy:
        device.remote_file_copy(model, dest=dest)

    spy.assert_not_called()
    assert device.check_file_exists(dest)
