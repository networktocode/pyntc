"""Integration tests for IOSDevice.remote_file_copy.

These tests connect to an actual Cisco IOS device in the lab and are run manually.
They are NOT part of the CI unit test suite.

Usage (from project root):
    export IOS_HOST=<ios_ip>
    export IOS_USER=<user>
    export IOS_PASS=<pass>
    export FTP_URL=ftp://<ftp_user>:<ftp_password>@<server_ip>/<file_name>
    export TFTP_URL=tftp://<server_ip>/<file_name>
    export SCP_URL=scp://<scp_user>:<scp_password>@<server_ip>:2022/<file_name>
    export HTTP_URL=http://<http_user>:<http_password>@<server_ip>:8081/<file_name>
    export HTTPS_URL=https://<https_user>:<https_password>@<server_ip>:8443/<file_name>
    export SFTP_URL=sftp://<sftp_user>:<sftp_password>@<server_ip>:2022/<file_name>
    export FILE_CHECKSUM_MD5=<md5_hash>
    export FILE_SIZE=<image_size>
    export FILE_SIZE_UNIT=bytes       # optional; defaults to "bytes"
    # export IOS_VRF=Mgmt-vrf         # optional; applied to every copy test
    poetry run pytest tests/integration/test_ios_device.py -v

Set only the protocol URL vars for the servers you have available; each protocol
test skips automatically if its URL is not set. `conftest.py` maps this module
to md5 and copies `FILE_CHECKSUM_MD5` into `FILE_CHECKSUM` automatically.

Include the port in a URL whenever the service does not listen on the default.
IOS honors it, and the driver carries it through to the copy command.

Environment variables:
    IOS_HOST         - IP address or hostname of the lab IOS device
    IOS_USER         - SSH username
    IOS_PASS         - SSH password
    IOS_VRF          - Optional VRF name; when set, every copy test routes through this VRF
                       (needed when the file servers are only reachable via the management VRF).
                       IOS rejects the vrf keyword on http and https, and the driver omits it
                       for those two schemes.
    FTP_URL          - FTP URL of the file to transfer
    TFTP_URL         - TFTP URL of the file to transfer
    SCP_URL          - SCP URL of the file to transfer
    HTTP_URL         - HTTP URL of the file to transfer
    HTTPS_URL        - HTTPS URL of the file to transfer
    SFTP_URL         - SFTP URL of the file to transfer
    FILE_NAME        - Destination filename on the device (default: basename of URL path)
    FILE_CHECKSUM_MD5 - Expected md5 checksum of the file (shared across all protocols)
    FILE_SIZE        - Expected size of the file expressed in FILE_SIZE_UNIT units; used for
                       the pre-transfer free-space check
    FILE_SIZE_UNIT   - One of "bytes", "megabytes", or "gigabytes" (default: "bytes")
"""

import os

import pytest

from pyntc.devices import IOSDevice

from ._helpers import build_file_copy_model


@pytest.fixture(scope="module")
def device():
    """Connect to the lab IOS device. Skips all tests if credentials are not set."""
    host = os.environ.get("IOS_HOST")
    user = os.environ.get("IOS_USER")
    password = os.environ.get("IOS_PASS")

    if not all([host, user, password]):
        pytest.skip("IOS_HOST / IOS_USER / IOS_PASS environment variables not set")

    dev = IOSDevice(host, user, password)
    yield dev
    dev.close()


def _build_ios_file_copy_model(env_var):
    """Wrap `build_file_copy_model` to stamp `IOS_VRF` onto the model.

    IOS file servers are often only reachable via the management VRF, so the
    device's `copy` command needs `vrf <name>` appended. The shared helper
    has no concept of VRF; this driver-local wrapper bridges that gap without
    leaking IOS specifics into the shared helper.
    """
    model = build_file_copy_model(env_var)
    vrf = os.environ.get("IOS_VRF")
    if vrf:
        model.vrf = vrf
    return model


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
    checksum = device.get_remote_checksum(
        any_file_copy_model.file_name, hashing_algorithm=any_file_copy_model.hashing_algorithm
    )
    assert checksum and len(checksum) > 0


def test_remote_file_copy_ftp(device):
    """Transfer the file using FTP and verify it exists on the device.

    IOS never prompts for FTP credentials. This test fails against a driver that
    sends the source URL without them, because the device attempts an anonymous
    login and the server refuses it.
    """
    model = _build_ios_file_copy_model("FTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_tftp(device):
    """Transfer the file using TFTP and verify it exists on the device."""
    model = _build_ios_file_copy_model("TFTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_scp(device):
    """Transfer the file using SCP and verify it exists on the device.

    IOS prompts for the source username and the password here, so the driver
    sends a URL with no credentials and answers the prompts from the model.
    """
    model = _build_ios_file_copy_model("SCP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_http(device):
    """Transfer the file using HTTP and verify it exists on the device."""
    model = _build_ios_file_copy_model("HTTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_https(device):
    """Transfer the file using HTTPS and verify it exists on the device.

    An IOS release with a dated TLS stack can fail the handshake against a modern
    server. That is a device and server mismatch rather than a driver defect.
    """
    model = _build_ios_file_copy_model("HTTPS_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)


def test_remote_file_copy_sftp(device):
    """Transfer the file using SFTP and verify it exists on the device."""
    model = _build_ios_file_copy_model("SFTP_URL")
    device.remote_file_copy(model)
    assert device.check_file_exists(model.file_name)
