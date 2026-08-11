"""Unit tests for the ``arista_eos_ssh`` driver.

Fixtures are a real ``show ... | json`` capture from a DCS-7050TX-64-R running EOS 4.28.5M
(serial, MACs and one port description sanitised). Real hardware output covers two shapes
the older vEOS fixtures did not: ``softwareImage`` carrying a ``flash:/`` prefix, and a
routed ``Management1`` whose ``vlanInformation`` has no ``vlanId`` at all.

Because the two drivers no longer share fixture data,
``test_facts_match_eapi_driver_for_identical_payload`` is what guards against drift: it
feeds the same document to both drivers and asserts every fact comes out identical.
"""

import hashlib
import inspect
import json
import os
import time
from unittest import mock

import pytest

from pyntc import ntc_device
from pyntc.devices import EOSDevice, EOSSSHDevice
from pyntc.devices.base_device import RollbackError
from pyntc.devices.eos_device import DEFAULT_REBOOT_TIMEOUT
from pyntc.devices.eos_ssh_device import DEFAULT_READ_TIMEOUT
from pyntc.devices.eos_ssh_device import EOSSSHDevice as Driver
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileTransferError,
    NotEnoughFreeSpaceError,
    OSInstallError,
    SocketClosedError,
)
from pyntc.utils.models import FileCopyModel

BOOT_TIMESTAMP = 1785963023.376446
MODEL = "DCS-7050TX-64-R"
OS_VERSION = "4.28.5M-29792660.4285M"
HOSTNAME = "nyc-eos-01"
SERIAL_NUMBER = "JPE00000000"
BOOT_IMAGE = "EOS-4.28.5M.swi"
FREE_BYTES = 1327603712
INTERFACE_COUNT = 65


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_registered_device_type():
    with mock.patch.object(EOSSSHDevice, "open"):
        device = ntc_device("arista_eos_ssh", "host", "user", "password")
    assert isinstance(device, EOSSSHDevice)
    assert device.device_type == "arista_eos_ssh"


def test_vendor(eos_ssh_device):
    assert eos_ssh_device.vendor == "arista"


# ---------------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------------


def test_init_defaults():
    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler"):
        device = EOSSSHDevice("host", "user", "password")
    assert device.port == 22
    assert device.secret == ""
    assert device.device_type == "arista_eos_ssh"


def test_init_accepts_port_and_secret():
    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler"):
        device = EOSSSHDevice("host", "user", "password", secret="enable_me", port="2222")
    assert device.port == 2222
    assert device.secret == "enable_me"


def test_init_does_not_build_an_eapi_connection():
    # EOSDevice.__init__ would call pyeapi.connect(); the SSH driver must not.
    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler"):
        with mock.patch("pyntc.devices.eos_device.eos_connect") as mock_connect:
            EOSSSHDevice("host", "user", "password")
    mock_connect.assert_not_called()


def test_open_connects_with_arista_eos_driver():
    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler") as ch:
        EOSSSHDevice("host", "user", "password", port=2222, secret="s3cret")
    _, kwargs = ch.call_args
    assert kwargs["device_type"] == "arista_eos"
    assert kwargs["host"] == "host"
    assert kwargs["port"] == 2222
    assert kwargs["secret"] == "s3cret"


def test_open_passes_extra_netmiko_kwargs():
    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler") as ch:
        EOSSSHDevice("host", "user", "password", global_delay_factor=2)
    assert ch.call_args[1]["global_delay_factor"] == 2


def test_open_is_noop_when_already_connected(eos_ssh_device):
    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler") as ch:
        eos_ssh_device.open()
    ch.assert_not_called()
    eos_ssh_device.native.find_prompt.assert_called()


def test_open_reconnects_when_session_is_dead():
    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler") as ch:
        device = EOSSSHDevice("host", "user", "password")
        assert ch.call_count == 1
        device.native.find_prompt.side_effect = OSError("socket closed")
        device.open()
        assert ch.call_count == 2
        assert device._connected is True


def test_native_ssh_is_native(eos_ssh_device):
    # Inherited file-transfer code reaches for native_ssh; it must be the Netmiko handler.
    assert eos_ssh_device.native_ssh is eos_ssh_device.native


def test_close_disconnects(eos_ssh_device):
    eos_ssh_device.close()
    eos_ssh_device.native.disconnect.assert_called_once()
    assert eos_ssh_device._connected is False


def test_close_is_idempotent(eos_ssh_device):
    eos_ssh_device.close()
    eos_ssh_device.close()
    eos_ssh_device.native.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# show()
# ---------------------------------------------------------------------------


def test_show_single_command_returns_dict(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    result = device.show("show version")
    assert isinstance(result, dict)
    assert result["modelName"] == MODEL
    device.native.send_command.assert_called_with("show version | json", read_timeout=DEFAULT_READ_TIMEOUT)


def test_show_list_returns_list(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json", "show_hostname_json"])
    results = device.show(["show version", "show hostname"])
    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["modelName"] == MODEL
    assert results[1]["hostname"] == HOSTNAME


def test_show_raw_text_returns_str_without_json_pipe(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir"])
    result = device.show("dir", raw_text=True)
    assert isinstance(result, str)
    assert "bytes free" in result
    device.native.send_command.assert_called_with("dir", read_timeout=DEFAULT_READ_TIMEOUT)


def test_show_raw_text_list(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "show_boot"])
    results = device.show(["dir", "show boot"], raw_text=True)
    assert [isinstance(item, str) for item in results] == [True, True]


@pytest.mark.parametrize(
    "command",
    [
        "reload now",
        "copy running-config startup-config",
        "configure replace flash:cp force",
        "install source flash:EOS.swi",
    ],
)
def test_show_does_not_pipe_non_show_commands_to_json(eos_ssh_send_command, command):
    # "reload now | json" is not a valid command. Non-show commands must go through bare,
    # and every inherited caller discards the return value, so {} preserves the contract.
    device = eos_ssh_send_command([""])
    result = device.show(command)
    assert result == {}
    assert device.native.send_command.call_args[0][0] == command


def test_show_raises_command_error(eos_ssh_send_command):
    device = eos_ssh_send_command(["% Invalid input (at token 1: 'bogus')"])
    with pytest.raises(CommandError) as err:
        device.show("show bogus")
    # The caller's command, not the wire command -- errors must not leak the "| json"
    # suffix, matching the plain command name pyeapi reports on EOSDevice.
    assert err.value.command == "show bogus"
    assert "Invalid input" in err.value.cli_error_msg


def test_show_list_raises_command_list_error(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json", "% Invalid input"])
    with pytest.raises(CommandListError) as err:
        device.show(["show version", "show bogus"])
    assert err.value.commands == ["show version", "show bogus"]
    assert err.value.command == "show bogus"


def test_show_raises_when_output_is_not_json(eos_ssh_send_command):
    # A command with no JSON renderer must raise, never silently fall back to text
    # parsing -- a fallback returns a differently shaped document and yields wrong facts.
    device = eos_ssh_send_command(["This command is not converted to JSON"])
    with pytest.raises(CommandError) as err:
        device.show("show something-unconverted")
    assert "does not support JSON output" in err.value.cli_error_msg


def test_show_list_raises_command_list_error_when_output_is_not_json(eos_ssh_send_command):
    # The list contract must hold for JSON parse failures too, not only device-reported
    # errors: a non-JSON response mid-list raises CommandListError, never bare CommandError.
    device = eos_ssh_send_command(["show_version_json", "This command is not converted to JSON"])
    with pytest.raises(CommandListError) as err:
        device.show(["show version", "show something-unconverted"])
    assert err.value.commands == ["show version", "show something-unconverted"]
    assert err.value.command == "show something-unconverted"


def test_show_reopens_connection(eos_ssh_send_command):
    # Guards reboot polling: _wait_for_device_reboot survives only because show() re-opens.
    device = eos_ssh_send_command(["show_version_json"])
    with mock.patch.object(Driver, "open") as mock_open:
        device.show("show version")
    mock_open.assert_called_once()


@pytest.mark.parametrize(
    "command,expected_timeout",
    [
        ("install source flash:EOS.swi", 3600),
        ("copy running-config startup-config", 300),
        ("configure replace flash:cp force", 300),
        ("show running-config", 120),
        ("show startup-config", 120),
        ("show version", DEFAULT_READ_TIMEOUT),
    ],
)
def test_show_resolves_read_timeout_per_command(eos_ssh_send_command, command, expected_timeout):
    # Timeouts are derived from the command text so show()'s signature can stay identical
    # to EOSDevice.show() while inherited long-running callers still work.
    device = eos_ssh_send_command(['{"x": 1}'])
    device.show(command, raw_text=True)
    assert device.native.send_command.call_args[1]["read_timeout"] == expected_timeout


# ---------------------------------------------------------------------------
# config()
# ---------------------------------------------------------------------------


def test_config_single_command_returns_none(eos_ssh_config):
    device = eos_ssh_config([""])
    assert device.config("interface Ethernet1") is None
    device.native.send_config_set.assert_called_with("interface Ethernet1", exit_config_mode=False)


def test_config_list_returns_none(eos_ssh_config):
    device = eos_ssh_config(["", ""])
    assert device.config(["interface Ethernet1", "no shutdown"]) is None
    assert device.native.send_config_set.call_count == 2


def test_config_exits_config_mode(eos_ssh_config):
    device = eos_ssh_config([""])
    device.config("interface Ethernet1")
    device.native.exit_config_mode.assert_called_once()


def test_config_raises_command_error(eos_ssh_config):
    device = eos_ssh_config(["% Invalid input"])
    with pytest.raises(CommandError) as err:
        device.config("bogus command")
    assert err.value.command == "bogus command"


def test_config_list_raises_command_list_error(eos_ssh_config):
    device = eos_ssh_config(["", "% Invalid input"])
    with pytest.raises(CommandListError) as err:
        device.config(["interface Ethernet1", "bogus"])
    assert err.value.command == "bogus"
    assert err.value.commands == ["interface Ethernet1", "bogus"]


def test_config_exits_config_mode_on_error(eos_ssh_config):
    # A failed command must not leave the session parked in config mode.
    device = eos_ssh_config(["% Invalid input"])
    with pytest.raises(CommandError):
        device.config("bogus command")
    device.native.exit_config_mode.assert_called_once()


# ---------------------------------------------------------------------------
# Fact properties -- expectations match test_eos_device.py exactly
# ---------------------------------------------------------------------------


def test_hostname(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_hostname_json"])
    assert device.hostname == HOSTNAME


def test_fqdn(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_hostname_json"])
    assert device.fqdn == HOSTNAME


def test_model(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    assert device.model == MODEL


def test_os_version(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    assert device.os_version == OS_VERSION


def test_serial_number(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    assert device.serial_number == SERIAL_NUMBER


def test_boot_time(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    boot_time = device.boot_time
    assert isinstance(boot_time, float)
    assert boot_time == BOOT_TIMESTAMP


def test_uptime(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    uptime = device.uptime
    assert isinstance(uptime, int)
    assert uptime == pytest.approx(int(time.time() - BOOT_TIMESTAMP), abs=2)


def test_uptime_string(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    with mock.patch.object(Driver, "_uptime_to_string", return_value="02:00:03:38"):
        assert device.uptime_string == "02:00:03:38"


def test_interfaces(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_interfaces_status_json"])
    interfaces = device.interfaces
    assert len(interfaces) == INTERFACE_COUNT
    # Sorted lexicographically, matching EOSDevice: "Ethernet10" precedes "Ethernet2".
    assert interfaces == sorted(interfaces)
    assert interfaces[:3] == ["Ethernet1", "Ethernet10", "Ethernet11"]
    assert interfaces[-1] == "Management1"
    assert "Ethernet49/1" in interfaces


def test_routed_interface_without_vlan_id(eos_ssh_send_command):
    # Management1 is routed: its vlanInformation carries no vlanId. The key map must
    # resolve that to None rather than raising.
    device = eos_ssh_send_command(["show_interfaces_status_json"])
    management = [i for i in device._interfaces_status_list() if i["interface"] == "Management1"][0]
    assert management["vlan"] is None
    assert management["state"] == "connected"


def test_vlans(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_vlan_json"])
    # Lexicographic ordering, matching EOSVlans.get_list() -- so "9" sorts last.
    assert device.vlans == ["1", "10", "11", "12", "9"]


def test_vlans_uses_show_vlan_not_pyeapi_api(eos_ssh_send_command):
    # EOSVlans reaches for device.native.api("vlans"), which does not exist over SSH.
    device = eos_ssh_send_command(["show_vlan_json"])
    device.vlans  # noqa: B018
    assert device.native.send_command.call_args[0][0] == "show vlan | json"
    device.native.api.assert_not_called()


def test_boot_options_strips_flash_prefix(eos_ssh_send_command):
    # Real hardware returns softwareImage as "flash:/EOS-4.28.5M.swi"; the vEOS fixture had
    # no prefix, so boot_options' .replace("flash:/", "") was previously untested.
    device = eos_ssh_send_command(["show_boot-config_json"])
    assert device.boot_options == {"sys": BOOT_IMAGE}


def test_running_config(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_running-config"])
    running_config = device.running_config
    assert isinstance(running_config, str)
    assert "hostname eos-spine1" in running_config
    device.native.send_command.assert_called_with("show running-config", read_timeout=120)


def test_startup_config(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_startup-config"])
    assert "hostname eos-spine1" in device.startup_config


def test_facts_are_cached(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_hostname_json"])
    assert device.hostname == HOSTNAME
    assert device.hostname == HOSTNAME
    # A single device round-trip: the second read comes from the cache.
    assert device.native.send_command.call_count == 1


def test_backup_running_config(eos_ssh_send_command, tmp_path):
    # Inherited backup_running_config reads running_config twice (once to write, once to
    # log) and running_config is not cached, so two round-trips are expected.
    device = eos_ssh_send_command(["show_running-config", "show_running-config"])
    target = tmp_path / "backup.cfg"
    device.backup_running_config(str(target))
    assert "hostname eos-spine1" in target.read_text()


# ---------------------------------------------------------------------------
# Filesystem helpers (inherited, exercised over SSH)
# ---------------------------------------------------------------------------


def test_get_file_system(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir"])
    assert device._get_file_system() == "flash:"


def test_get_free_space(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir"])
    assert device._get_free_space() == FREE_BYTES


def test_get_free_space_raises_when_unparseable(eos_ssh_send_command):
    device = eos_ssh_send_command(["nothing useful here"])
    with pytest.raises(CommandError):
        device._get_free_space()


def test_check_free_space_raises_when_insufficient(eos_ssh_send_command):
    from pyntc.errors import NotEnoughFreeSpaceError

    device = eos_ssh_send_command(["dir"])
    with pytest.raises(NotEnoughFreeSpaceError):
        device._check_free_space(99_999_999_999, file_system="flash:")


def test_image_booted(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_boot", "show_boot"])
    assert device._image_booted(BOOT_IMAGE) is True
    # The other image present on flash is not the booted one.
    assert device._image_booted("EOS-4.28.9M.swi") is False


# ---------------------------------------------------------------------------
# Inherited file operations (these already used Netmiko on the eAPI driver)
# ---------------------------------------------------------------------------


def test_check_file_exists_true(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "Directory of flash:/EOS.swi\n\n-rwx 1234 EOS.swi\n"])
    assert device.check_file_exists("EOS.swi") is True


def test_check_file_exists_false(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "% Error listing directory"])
    assert device.check_file_exists("missing.swi") is False


def test_check_file_exists_raises_on_unknown_output(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "something unexpected"])
    with pytest.raises(CommandError):
        device.check_file_exists("EOS.swi")


def test_get_remote_checksum(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "verify /sha512 (flash:EOS.swi) = abc123"])
    assert device.get_remote_checksum("EOS.swi", hashing_algorithm="sha512") == "abc123"


def test_get_remote_checksum_rejects_unsupported_algorithm(eos_ssh_device):
    with pytest.raises(ValueError, match="Unsupported hashing algorithm"):
        eos_ssh_device.get_remote_checksum("EOS.swi", hashing_algorithm="blake3")


def test_verify_file_matches(eos_ssh_send_command):
    device = eos_ssh_send_command(
        ["dir", "Directory of flash:/EOS.swi\n", "dir", "verify /md5 (flash:EOS.swi) = ABC123"]
    )
    assert device.verify_file("abc123", "EOS.swi") is True


def test_verify_file_missing_file(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "No such file"])
    assert device.verify_file("abc123", "EOS.swi") is False


# ---------------------------------------------------------------------------
# Pushing code onto the box: file_copy (local -> device, over SCP)
# ---------------------------------------------------------------------------


def test_file_copy_instance_uses_the_netmiko_session(eos_ssh_device):
    # The whole reason native_ssh is aliased: inherited FileTransfer code must receive the
    # SSH driver's own Netmiko handler, not a separate session.
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        eos_ssh_device._file_copy_instance("/local/EOS.swi", "EOS.swi", file_system="flash:")
    args, kwargs = file_transfer.call_args
    assert args[0] is eos_ssh_device.native
    # "flash:" is the CLI name; SCP addresses the same filesystem by its Linux path.
    assert kwargs["file_system"] == "/mnt/flash"


@pytest.fixture
def local_image(tmp_path):
    """A small local file plus its md5, standing in for an image to upload."""
    source = tmp_path / "EOS.swi"
    source.write_bytes(b"x" * 32)
    return source, hashlib.md5(b"x" * 32).hexdigest()  # noqa: S324


def _present(checksum):
    """Side effects for a verify_file() that finds a matching remote file."""
    return ["Directory of flash:/EOS.swi\n", f"verify /md5 (flash:EOS.swi) = {checksum}"]


ABSENT = ["No such file"]


def test_file_copy_skips_transfer_when_already_present(eos_ssh_send_command, local_image):
    source, checksum = local_image
    device = eos_ssh_send_command(["dir", *_present(checksum)])
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        device.file_copy(str(source))
    file_transfer.return_value.transfer_file.assert_not_called()


def test_file_copy_transfers_when_missing(eos_ssh_send_command, local_image):
    source, checksum = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir", *_present(checksum)])
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        device.file_copy(str(source))
    file_transfer.return_value.establish_scp_conn.assert_called_once()
    file_transfer.return_value.transfer_file.assert_called_once()
    file_transfer.return_value.close_scp_chan.assert_called_once()
    # Arista's FileTransfer raises NotImplementedError here, so it must never be called.
    file_transfer.return_value.enable_scp.assert_not_called()


def test_file_copy_never_enters_the_shell(eos_ssh_send_command, local_image):
    # The reason this override exists: the connecting account may have no bash access.
    source, checksum = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir", *_present(checksum)])
    with mock.patch("pyntc.devices.eos_device.FileTransfer"):
        device.file_copy(str(source))
    commands = [call[0][0] for call in device.native.send_command.call_args_list]
    assert not any(command.strip() == "bash" or command.startswith("/bin/") for command in commands)


def test_file_copy_verifies_over_the_cli(eos_ssh_send_command, local_image):
    source, checksum = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir", *_present(checksum)])
    with mock.patch("pyntc.devices.eos_device.FileTransfer"):
        device.file_copy(str(source))
    commands = [call[0][0] for call in device.native.send_command.call_args_list]
    assert "dir flash:/EOS.swi" in commands
    assert "verify /md5 flash:EOS.swi" in commands


def test_file_copy_raises_when_transfer_fails(eos_ssh_send_command, local_image):
    source, _ = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir"])
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        file_transfer.return_value.transfer_file.side_effect = RuntimeError("scp blew up")
        with pytest.raises(FileTransferError):
            device.file_copy(str(source))
    # The SCP channel must be closed even when the transfer blows up.
    file_transfer.return_value.close_scp_chan.assert_called_once()


def test_file_copy_raises_socket_closed_when_session_drops_and_file_missing(eos_ssh_send_command, local_image):
    source, _ = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir"])
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        file_transfer.return_value.transfer_file.side_effect = OSError("socket closed")
        file_transfer.return_value.compare_md5.return_value = False
        with pytest.raises(SocketClosedError):
            device.file_copy(str(source))


def test_file_copy_tolerates_dropped_session_when_file_landed(eos_ssh_send_command, local_image):
    # A dropped control channel is survivable if the file actually made it.
    source, checksum = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir", *_present(checksum)])
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        file_transfer.return_value.transfer_file.side_effect = OSError("socket closed")
        file_transfer.return_value.compare_md5.return_value = True
        device.file_copy(str(source))


def test_file_copy_raises_when_file_absent_after_transfer(eos_ssh_send_command, local_image):
    source, _ = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir", *ABSENT])
    with mock.patch("pyntc.devices.eos_device.FileTransfer"):
        with pytest.raises(FileTransferError):
            device.file_copy(str(source))


def test_file_copy_raises_when_not_enough_free_space(eos_ssh_send_command, local_image):
    source, _ = local_image
    device = eos_ssh_send_command(["dir", *ABSENT, "dir"])
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        with mock.patch("os.path.getsize", return_value=FREE_BYTES + 1):
            with pytest.raises(NotEnoughFreeSpaceError):
                device.file_copy(str(source))
    file_transfer.return_value.transfer_file.assert_not_called()


def test_file_copy_remote_exists_true(eos_ssh_send_command, local_image):
    source, checksum = local_image
    device = eos_ssh_send_command(["dir", *_present(checksum)])
    assert device.file_copy_remote_exists(str(source)) is True


def test_file_copy_remote_exists_false_when_checksum_differs(eos_ssh_send_command, local_image):
    source, _ = local_image
    device = eos_ssh_send_command(["dir", *_present("deadbeef")])
    assert device.file_copy_remote_exists(str(source)) is False


def test_file_copy_accepts_explicit_file_system_and_dest(eos_ssh_send_command, local_image):
    # With both supplied there is no "dir" filesystem probe -- verification goes first.
    source, checksum = local_image
    device = eos_ssh_send_command(
        ["Directory of flash:/boot.swi\n", f"verify /md5 (flash:boot.swi) = {checksum}"],
    )
    with mock.patch("pyntc.devices.eos_device.FileTransfer") as file_transfer:
        device.file_copy(str(source), dest="boot.swi", file_system="flash:")
    file_transfer.return_value.transfer_file.assert_not_called()
    assert device.native.send_command.call_args_list[0][0][0] == "dir flash:/boot.swi"


def test_file_copy_remote_exists_accepts_explicit_file_system(eos_ssh_send_command, local_image):
    source, checksum = local_image
    device = eos_ssh_send_command(_present(checksum))
    assert device.file_copy_remote_exists(str(source), file_system="flash:") is True


def test_file_copy_remote_exists_never_enters_the_shell(eos_ssh_send_command, local_image):
    source, checksum = local_image
    device = eos_ssh_send_command(["dir", *_present(checksum)])
    device.file_copy_remote_exists(str(source))
    commands = [call[0][0] for call in device.native.send_command.call_args_list]
    assert not any(command.strip() == "bash" or command.startswith("/bin/") for command in commands)


# ---------------------------------------------------------------------------
# Pulling code onto the box: remote_file_copy (device fetches from a server)
# ---------------------------------------------------------------------------


def _model(url="http://192.0.2.5/EOS.swi", checksum="abc123", **kwargs):
    return FileCopyModel(download_url=url, checksum=checksum, file_name="EOS.swi", **kwargs)


def test_remote_file_copy_issues_copy_command_and_verifies(eos_ssh_send_command):
    device = eos_ssh_send_command(
        [
            "dir",  # _get_file_system
            "",  # the copy command itself
            "Directory of flash:/EOS.swi\n",  # verify_file -> check_file_exists
            "verify /md5 (flash:EOS.swi) = abc123",  # verify_file -> get_remote_checksum
        ]
    )
    device.remote_file_copy(_model())
    commands = [call[0][0] for call in device.native.send_command.call_args_list]
    assert "copy http://192.0.2.5/EOS.swi flash:" in commands


def test_remote_file_copy_embeds_credentials_for_http(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "", "Directory of flash:/EOS.swi\n", "verify /md5 (flash:EOS.swi) = abc123"])
    device.remote_file_copy(_model(url="http://user:token@192.0.2.5/EOS.swi"))
    commands = [call[0][0] for call in device.native.send_command.call_args_list]
    assert "copy http://user:token@192.0.2.5/EOS.swi flash:" in commands


def test_remote_file_copy_prompts_for_scp_password(eos_ssh_send_command, eos_ssh_send_command_timing):
    # SCP cannot carry the password in the URL, so the driver answers the prompt interactively.
    device = eos_ssh_send_command(["dir", "Directory of flash:/EOS.swi\n", "verify /md5 (flash:EOS.swi) = abc123"])
    eos_ssh_send_command_timing(["Password:", ""], existing_device=device)
    device.remote_file_copy(_model(url="scp://user:token@192.0.2.5/EOS.swi"))
    timing_commands = [call[0][0] for call in device.native.send_command_timing.call_args_list]
    assert timing_commands[0] == "copy scp://user@192.0.2.5/EOS.swi flash:"
    assert timing_commands[1] == "token"  # the password, sent only after the prompt appears


def test_remote_file_copy_rejects_non_model(eos_ssh_device):
    with pytest.raises(TypeError):
        eos_ssh_device.remote_file_copy("http://192.0.2.5/EOS.swi")


def test_remote_file_copy_rejects_unsupported_scheme(eos_ssh_device):
    with pytest.raises(ValueError, match="Unsupported scheme"):
        eos_ssh_device.remote_file_copy(_model(url="rsync://192.0.2.5/EOS.swi"))


def test_remote_file_copy_rejects_query_string(eos_ssh_device):
    # The EOS CLI cannot handle "?" in a copy URL.
    with pytest.raises(ValueError, match="query strings"):
        eos_ssh_device.remote_file_copy(_model(url="https://192.0.2.5/EOS.swi?token=x"))


def test_remote_file_copy_checks_free_space_first(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "dir"])
    with pytest.raises(NotEnoughFreeSpaceError):
        device.remote_file_copy(_model(file_size=10, file_size_unit="gigabytes"))
    # Nothing was transferred.
    commands = [call[0][0] for call in device.native.send_command.call_args_list]
    assert not any(command.startswith("copy ") for command in commands)


def test_remote_file_copy_raises_on_error_output(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "Error: connection refused"])
    with pytest.raises(FileTransferError):
        device.remote_file_copy(_model())


def test_remote_file_copy_raises_when_checksum_mismatches(eos_ssh_send_command):
    device = eos_ssh_send_command(
        ["dir", "", "Directory of flash:/EOS.swi\n", "verify /md5 (flash:EOS.swi) = deadbeef"]
    )
    with pytest.raises(FileTransferError):
        device.remote_file_copy(_model(checksum="abc123"))


# ---------------------------------------------------------------------------
# Upgrading: install_os
# ---------------------------------------------------------------------------

NEW_IMAGE = "EOS-4.28.9M.swi"
NEW_IMAGE_BOOTED = "Software image: flash:/EOS-4.28.9M.swi\n"


def _set_boot_options_effects():
    """Side effects consumed by set_boot_options: fs probe, dir listing, install, readback."""
    return ["dir", "dir", "", '{"softwareImage": "flash:/EOS-4.28.9M.swi"}']


def test_install_os_returns_false_when_image_already_booted(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_boot"])
    assert device.install_os(BOOT_IMAGE) is False


def test_install_os_sets_boot_options_then_reboots(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_boot", *_set_boot_options_effects(), NEW_IMAGE_BOOTED])
    with mock.patch.object(Driver, "reboot") as mock_reboot:
        assert device.install_os(NEW_IMAGE) is True
    mock_reboot.assert_called_once_with(wait_for_reload=True, timeout=DEFAULT_REBOOT_TIMEOUT)
    commands = [call[0][0] for call in device.native.send_command.call_args_list]
    assert f"install source flash:{NEW_IMAGE}" in commands


def test_install_os_honours_custom_timeout(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_boot", *_set_boot_options_effects(), NEW_IMAGE_BOOTED])
    with mock.patch.object(Driver, "reboot") as mock_reboot:
        device.install_os(NEW_IMAGE, timeout=120)
    mock_reboot.assert_called_once_with(wait_for_reload=True, timeout=120)


def test_install_os_without_reboot_does_not_reboot(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_boot", *_set_boot_options_effects()])
    with mock.patch.object(Driver, "reboot") as mock_reboot:
        assert device.install_os(NEW_IMAGE, reboot=False) is True
    mock_reboot.assert_not_called()


def test_install_os_raises_when_image_not_booted_after_reboot(eos_ssh_send_command):
    # Device comes back still running the old image. The final side effect feeds
    # self.hostname, which OSInstallError reads when building its message.
    device = eos_ssh_send_command(["show_boot", *_set_boot_options_effects(), "show_boot", "show_hostname_json"])
    with mock.patch.object(Driver, "reboot"):
        with pytest.raises(OSInstallError):
            device.install_os(NEW_IMAGE)


# ---------------------------------------------------------------------------
# reboot / rollback / save
# ---------------------------------------------------------------------------


def test_reboot_sends_reload_now(eos_ssh_device):
    eos_ssh_device.reboot()
    eos_ssh_device.native.send_command_timing.assert_called_with("reload now")


def test_reboot_marks_session_disconnected(eos_ssh_device):
    eos_ssh_device.reboot()
    assert eos_ssh_device._connected is False


def test_reboot_tolerates_dropped_session(eos_ssh_device):
    # The session dies mid-command by design; that must not surface as an error.
    eos_ssh_device.native.send_command_timing.side_effect = OSError("Socket is closed")
    eos_ssh_device.reboot()
    assert eos_ssh_device._connected is False


def test_reboot_without_wait_does_not_poll(eos_ssh_device):
    with mock.patch.object(Driver, "_wait_for_device_reboot") as mock_wait:
        eos_ssh_device.reboot()
    mock_wait.assert_not_called()


def test_reboot_wait_for_reload_polls_with_original_boot_time(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_version_json"])
    with mock.patch.object(Driver, "_wait_for_device_reboot") as mock_wait:
        device.reboot(wait_for_reload=True, timeout=42)
    mock_wait.assert_called_once_with(original_boot_time=BOOT_TIMESTAMP, timeout=42)


def test_reboot_warns_on_deprecated_confirm(eos_ssh_device, caplog):
    eos_ssh_device.reboot(confirm=True)
    assert "deprecated" in caplog.text


def test_vlans_are_cached(eos_ssh_send_command):
    device = eos_ssh_send_command(["show_vlan_json"])
    assert device.vlans == ["1", "10", "11", "12", "9"]
    assert device.vlans == ["1", "10", "11", "12", "9"]
    assert device.native.send_command.call_count == 1


def test_rollback(eos_ssh_send_command):
    device = eos_ssh_send_command([""])
    device.rollback("good_checkpoint")
    assert device.native.send_command.call_args[0][0] == "configure replace good_checkpoint force"


def test_rollback_raises_on_failure(eos_ssh_send_command):
    device = eos_ssh_send_command(["% Invalid input"])
    with pytest.raises(RollbackError):
        device.rollback("bad_checkpoint")


def test_save(eos_ssh_send_command):
    device = eos_ssh_send_command([""])
    assert device.save() is True
    assert device.native.send_command.call_args[0][0] == "copy running-config startup-config"


def test_checkpoint(eos_ssh_send_command):
    device = eos_ssh_send_command([""])
    device.checkpoint("good_checkpoint")
    assert device.native.send_command.call_args[0][0] == "copy running-config good_checkpoint"


def test_set_boot_options(eos_ssh_send_command):
    # Side effects: _get_file_system, dir <fs>, install source, then boot_options readback.
    device = eos_ssh_send_command(
        ["dir", "dir", "", '{"softwareImage": "flash:/EOS-4.28.9M.swi"}'],
    )
    device.set_boot_options("EOS-4.28.9M.swi")
    calls = [call[0][0] for call in device.native.send_command.call_args_list]
    assert "install source flash:EOS-4.28.9M.swi" in calls


def test_set_boot_options_uses_long_read_timeout(eos_ssh_send_command):
    device = eos_ssh_send_command(
        ["dir", "dir", "", '{"softwareImage": "flash:/EOS-4.28.9M.swi"}'],
    )
    device.set_boot_options("EOS-4.28.9M.swi")
    install_call = [c for c in device.native.send_command.call_args_list if "install source" in c[0][0]][0]
    assert install_call[1]["read_timeout"] == 3600


def test_set_boot_options_missing_image(eos_ssh_send_command):
    from pyntc.errors import NTCFileNotFoundError

    # Third side effect feeds self.hostname, which NTCFileNotFoundError reads.
    device = eos_ssh_send_command(["dir", "dir", "show_hostname_json"])
    with pytest.raises(NTCFileNotFoundError):
        device.set_boot_options("not-on-the-box.swi")


def test_set_boot_options_raises_when_readback_mismatches(eos_ssh_send_command):
    device = eos_ssh_send_command(["dir", "dir", "", '{"softwareImage": "flash:/EOS-4.28.5M.swi"}'])
    with pytest.raises(CommandError):
        device.set_boot_options("EOS-4.28.9M.swi")


def test_install_mode_remains_unimplemented(eos_ssh_device):
    # EOSDevice does not implement install_mode; parity means neither does this driver.
    with pytest.raises(NotImplementedError):
        eos_ssh_device.install_mode  # noqa: B018


# ---------------------------------------------------------------------------
# API parity with EOSDevice
# ---------------------------------------------------------------------------

# EOSDevice assigns native_ssh as an *instance* attribute inside open(); the SSH driver
# exposes it as a class-level property so inherited code resolves it. That is the only
# permitted addition to the public surface.
KNOWN_ADDITIONS = {"native_ssh"}


def _fixture(name):
    path = os.path.join(os.path.dirname(__file__), "device_mocks", "eos_ssh", name)
    with open(path) as handle:
        return json.load(handle)


# Facts derived purely from show output. "vlans" is excluded: EOSDevice sources it from
# pyeapi's native.api("vlans"), which has no SSH equivalent by design.
SHARED_FACTS = ["boot_time", "hostname", "fqdn", "model", "os_version", "serial_number", "interfaces", "boot_options"]


@pytest.mark.parametrize("fact", SHARED_FACTS)
def test_facts_match_eapi_driver_for_identical_payload(fact):
    """Both drivers must derive identical facts from identical device output.

    The two drivers no longer share fixture files, so this is the anti-drift guard: feed
    the same documents to each and require the same answer.
    """
    payloads = {
        "show version": _fixture("show_version_json"),
        "show hostname": _fixture("show_hostname_json"),
        "show interfaces status": _fixture("show_interfaces_status_json"),
        "show boot-config": _fixture("show_boot-config_json"),
    }

    def fake_show(command, raw_text=False):
        return payloads[command]

    with mock.patch("pyntc.devices.eos_ssh_device.ConnectHandler"):
        ssh_device = EOSSSHDevice("host", "user", "password")
    with mock.patch("pyeapi.client.Node", autospec=True):
        with mock.patch("pyntc.devices.eos_device.eos_connect"):
            eapi_device = EOSDevice("host", "user", "password")

    with mock.patch.object(ssh_device, "show", side_effect=fake_show):
        with mock.patch.object(eapi_device, "show", side_effect=fake_show):
            assert getattr(ssh_device, fact) == getattr(eapi_device, fact)


def _public_api(cls):
    return {name for name in dir(cls) if not name.startswith("_")}


def test_public_api_matches_eos_device():
    assert _public_api(EOSSSHDevice) - KNOWN_ADDITIONS == _public_api(EOSDevice)


def test_no_eos_device_member_is_missing():
    assert _public_api(EOSDevice) - _public_api(EOSSSHDevice) == set()


@pytest.mark.parametrize("name", sorted(_public_api(EOSDevice)))
def test_member_parity(name):
    eapi_attr = inspect.getattr_static(EOSDevice, name)
    ssh_attr = inspect.getattr_static(EOSSSHDevice, name)
    assert isinstance(ssh_attr, property) == isinstance(eapi_attr, property), f"{name} kind differs"
    if callable(eapi_attr) and not isinstance(eapi_attr, property):
        assert inspect.signature(ssh_attr) == inspect.signature(eapi_attr), f"{name} signature differs"
