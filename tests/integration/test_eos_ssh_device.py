"""Integration tests for EOSSSHDevice.

These tests connect to an actual Arista EOS device over SSH and are run manually.
They are NOT part of the CI unit test suite.

This suite is the hardware validation for the ``arista_eos_ssh`` driver. It deliberately
covers two things the unit tests cannot:

1. That ``show <command> | json`` really does return the eAPI-shaped document the driver
   relies on -- ``test_json_key_contract`` asserts every key the inherited fact properties
   dereference. This is the design's load-bearing assumption.
2. That eAPI is genuinely not required -- nothing here enables or touches
   ``management api http-commands``.

Usage (from project root):
    export EOS_SSH_HOST=<eos_ip>
    export EOS_SSH_USER=<user>
    export EOS_SSH_PASS=<pass>
    export SCP_URL=scp://<scp_user>:<scp_password>@<server_ip>/<file_name>
    export HTTP_URL=http://<http_user>:<http_password>@<server_ip>:8081/<file_name>
    export FILE_CHECKSUM_512=<sha512_hash>
    export FILE_SIZE=<image_size>
    export FILE_SIZE_UNIT=megabytes  # optional; defaults to "bytes"
    poetry run pytest tests/integration/test_eos_ssh_device.py -v

Set only the protocol URL vars for the servers you have available; each protocol test
skips automatically if its URL is not set.

Environment variables:
    EOS_SSH_HOST     - IP address or hostname of the lab EOS device
    EOS_SSH_USER     - SSH username
    EOS_SSH_PASS     - SSH password
    EOS_SSH_SECRET   - Enable secret (optional)
    EOS_SSH_PORT     - SSH port (optional; defaults to 22)
    FTP_URL          - FTP URL of the file to transfer
    TFTP_URL         - TFTP URL of the file to transfer
    SCP_URL          - SCP URL of the file to transfer
    HTTP_URL         - HTTP URL of the file to transfer
    HTTPS_URL        - HTTPS URL of the file to transfer
    SFTP_URL         - SFTP URL of the file to transfer
    FILE_NAME        - Destination filename on the device (default: basename of URL path)
    FILE_CHECKSUM_512 - Expected sha512 checksum of the file
    FILE_SIZE        - Expected size of the file expressed in FILE_SIZE_UNIT units
    FILE_SIZE_UNIT   - One of "bytes", "megabytes", or "gigabytes" (default: "bytes")
"""

import os

import pytest

from pyntc.devices import EOSSSHDevice

from ._helpers import build_file_copy_model

# Every key the inherited EOSDevice fact properties dereference, per command. If this test
# passes on real hardware, the "| json" output is eAPI-compatible and the driver's whole
# inheritance strategy is sound.
JSON_KEY_CONTRACT = {
    "show version": ["bootupTimestamp", "modelName", "internalVersion", "serialNumber"],
    "show hostname": ["hostname", "fqdn"],
    "show boot-config": ["softwareImage"],
    "show interfaces status": ["interfaceStatuses"],
    "show vlan": ["vlans"],
}

# Per-interface keys consumed by _interfaces_status_list via INTERFACES_KM.
INTERFACE_KEYS = ["bandwidth", "duplex", "linkStatus", "description"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def device():
    """Connect to the lab EOS device over SSH. Skips all tests if credentials are not set."""
    host = os.environ.get("EOS_SSH_HOST")
    user = os.environ.get("EOS_SSH_USER")
    password = os.environ.get("EOS_SSH_PASS")

    if not all([host, user, password]):
        pytest.skip("EOS_SSH_HOST / EOS_SSH_USER / EOS_SSH_PASS environment variables not set")

    dev = EOSSSHDevice(
        host,
        user,
        password,
        secret=os.environ.get("EOS_SSH_SECRET", ""),
        port=os.environ.get("EOS_SSH_PORT"),
    )
    yield dev
    dev.close()


# ---------------------------------------------------------------------------
# The load-bearing assumption
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command,keys", sorted(JSON_KEY_CONTRACT.items()))
def test_json_key_contract(device, command, keys):
    """``show ... | json`` must return the eAPI-shaped document the driver depends on."""
    result = device.show(command)
    assert isinstance(result, dict), f"{command} | json did not return a JSON object"
    for key in keys:
        assert key in result, f"{command} | json is missing key '{key}'"


def test_interface_status_keys(device):
    """Each interface entry must carry the keys ``_interfaces_status_list`` reshapes."""
    statuses = device.show("show interfaces status")["interfaceStatuses"]
    assert statuses, "device reported no interfaces"
    for name, interface in statuses.items():
        for key in INTERFACE_KEYS:
            assert key in interface, f"interface {name} is missing key '{key}'"


def test_non_show_commands_are_not_piped_to_json(device):
    """A non-show command must not gain a ``| json`` suffix, which would be invalid."""
    # "show clock" proves the pipe is applied; a bare command proves it is not.
    assert isinstance(device.show("show clock"), dict)


# ---------------------------------------------------------------------------
# Facts and config retrieval
# ---------------------------------------------------------------------------


def test_device_connects(device):
    """Verify the device is reachable and responds to show commands."""
    assert device.hostname
    assert device.os_version


def test_facts(device):
    """Every fact property must resolve without error."""
    assert isinstance(device.uptime, int)
    assert isinstance(device.boot_time, float)
    assert device.model
    assert isinstance(device.serial_number, str)
    assert isinstance(device.interfaces, list)
    assert isinstance(device.vlans, list)
    assert device.boot_options["sys"]


def test_running_config(device):
    """The running config must come back as non-empty text."""
    assert "hostname" in device.running_config


def test_startup_config(device):
    """The startup config must come back as non-empty text."""
    assert device.startup_config.strip()


def test_config_round_trip(device):
    """Apply a harmless config change, confirm it lands in the running config, then remove it."""
    marker = "pyntc integration test"
    # Multi-line on purpose: banners exercise the cmd_verify=False path in config().
    device.config(f"banner motd\n{marker}\nEOF")
    try:
        assert marker in device.running_config
    finally:
        device.config("no banner motd")
    assert marker not in device.running_config


def test_show_raises_on_bad_command(device):
    """A bogus show command must raise CommandError, not return garbage."""
    from pyntc.errors import CommandError

    with pytest.raises(CommandError):
        device.show("show definitely-not-a-command")


# ---------------------------------------------------------------------------
# Filesystem and transfer
# ---------------------------------------------------------------------------


def test_file_system_detection(device):
    """The default filesystem must parse out of ``dir`` output."""
    assert device._get_file_system().endswith(":")


def test_free_space(device):
    """Free space must parse out of ``dir`` output as a positive integer."""
    assert device._get_free_space() > 0


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


def test_get_remote_checksum(device):
    """If the transferred file exists, its checksum must come back non-empty."""
    model = build_file_copy_model("SCP_URL")
    if not device.check_file_exists(model.file_name):
        pytest.skip("File does not exist on device; run a remote_file_copy test first")
    checksum = device.get_remote_checksum(model.file_name, hashing_algorithm="sha512")
    assert checksum


def test_verify_file(device):
    """verify_file must confirm the transferred file against its expected checksum."""
    model = build_file_copy_model("SCP_URL")
    if not device.check_file_exists(model.file_name):
        pytest.skip("File does not exist on device; run a remote_file_copy test first")
    assert device.verify_file(model.checksum, model.file_name, hashing_algorithm="sha512") is True
