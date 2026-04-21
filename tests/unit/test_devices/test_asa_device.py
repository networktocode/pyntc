import os
from ipaddress import ip_address, ip_interface
from unittest import mock

import pytest

from pyntc.devices import ASADevice
from pyntc.devices import asa_device as asa_module
from pyntc.errors import CommandError, FileTransferError, NotEnoughFreeSpaceError
from pyntc.utils.models import FileCopyModel

from .device_mocks.asa import send_command

BOOT_IMAGE = "asa9-12-3-12-smp-k8.bin"
BOOT_OPTIONS_PATH = "pyntc.devices.asa_device.ASADevice.boot_options"
ACTIVE = "active"
STANDBY_READY = "standby ready"
NEGOTIATION = "negotiation"
FAILED = "failed"
NOT_DETECTED = "not detected"
COLD_STANDBY = "cold standby"
VERSION_DATA = {
    "version": "9.16(2)",
    "device_mgr_version": "7.16(1)",
    "image": "boot:/asa9162-smp-k8.bin",
    "hostname": "ciscoasa",
    "uptime": "2 hours 7 mins",
    "hardware": "ASAv, 2048 MB RAM, CPU Lynnfield 3695 MHz",
    "model": "",
    "flash": "8192MB",
    "interfaces": ["Management0/0", "GigabitEthernet0/0", "Internal-Data0/0"],
    "license_mode": "Smart Licensing",
    "license_state": "Unlicensed",
    "max_intf": "",
    "max_vlans": "50",
    "failover": "Active/Active",
    "cluster": "Disabled",
    "serial": "9ANMLKTFC5B",
    "last_mod": "cisco at 17:41:15.359 UTC Thu Dec 22 2022",
}


class TestASADevice:
    def setup_method(self, api):
        with mock.patch("pyntc.devices.asa_device.ConnectHandler") as api:
            if not getattr(self, "device", None):
                self.device = ASADevice("host", "user", "password")

            # need to think if there should be an if before this...
            self.device.native = api

            # counts how many times we setup and tear down
            if not getattr(self, "count_setup", None):
                self.count_setup = 0

            if not getattr(self, "count_teardown", None):
                self.count_teardown = 0

            self.device = ASADevice("host", "user", "password")
            api.send_command_timing.side_effect = send_command
            api.send_command.side_effect = send_command
            self.device.native = api
            self.count_setup += 1

    def teardown_method(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()
        self.count_teardown += 1

    def test_port(self):
        assert self.device.port == 22

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_boot_options_dir(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = f"Current BOOT variable = disk0:/{BOOT_IMAGE}"
        boot_options = self.device.boot_options
        assert boot_options == {"sys": BOOT_IMAGE}
        self.device.native.send_command_timing.assert_called_with("show boot | i BOOT variable")

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_boot_options_none(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = ""
        boot_options = self.device.boot_options
        assert boot_options["sys"] is None

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    @mock.patch.object(ASADevice, "config", return_value=None)
    def test_set_boot_options(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
            mock_cl.assert_called_with([f"boot system disk0:/{BOOT_IMAGE}"])

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    @mock.patch.object(ASADevice, "config", return_value=None)
    def test_set_boot_options_dir(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE, file_system="disk0:")
            mock_fs.assert_not_called()
            mock_cl.assert_called_with([f"boot system disk0:/{BOOT_IMAGE}"])

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_set_boot_options_no_file(self, mock_fs):
        with pytest.raises(asa_module.NTCFileNotFoundError):
            self.device.set_boot_options("bad_image.bin")

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    @mock.patch.object(ASADevice, "config", return_value=None)
    def test_set_boot_options_bad_boot(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": "bad_image.bin"}
            with pytest.raises(asa_module.CommandError):
                self.device.set_boot_options(BOOT_IMAGE)
                mock_boot.assert_called_once()

    def test_backup_running_config(self):
        filename = "local_running_config"
        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        assert contents == self.device.running_config
        os.remove(filename)

    def test_count_setup(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_setup == 1

    def test_count_teardown(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_teardown == 0


def test_enable_from_disable(asa_device):
    asa_device.native.check_enable_mode.return_value = False
    asa_device.native.check_config_mode.return_value = False
    asa_device.enable()
    asa_device.native.check_enable_mode.assert_called()
    asa_device.native.enable.assert_called()
    asa_device.native.check_config_mode.assert_called()
    asa_device.native.exit_config_mode.assert_not_called()


def test_enable_from_enable(asa_device):
    asa_device.native.check_enable_mode.return_value = True
    asa_device.native.check_config_mode.return_value = False
    asa_device.enable()
    asa_device.native.check_enable_mode.assert_called()
    asa_device.native.enable.assert_not_called()
    asa_device.native.check_config_mode.assert_called()
    asa_device.native.exit_config_mode.assert_not_called()


def test_enable_from_config(asa_device):
    asa_device.native.check_enable_mode.return_value = True
    asa_device.native.check_config_mode.return_value = True
    asa_device.enable()
    asa_device.native.check_enable_mode.assert_called()
    asa_device.native.enable.assert_not_called()
    asa_device.native.check_config_mode.assert_called()
    asa_device.native.exit_config_mode.assert_called()


def test_config(asa_device):
    command = "hostname DATA-CENTER-FW"
    asa_device.native.send_command_timing.return_value = ""

    result = asa_device.config(command)
    assert result is None

    asa_device.native.send_command_timing.assert_called_with(command)


def test_bad_config(asa_device):
    command = "asdf poknw"
    result = "Error: asdf"

    asa_device.native.send_command_timing.return_value = result
    with pytest.raises(asa_module.CommandError, match=command):
        asa_device.config(command)


def test_config_list(asa_device):
    commands = ["crypto key generate rsa modulus 2048", "aaa authentication ssh console LOCAL"]
    asa_device.native.send_command_timing.return_value = ""
    asa_device.config(commands)

    for cmd in commands:
        asa_device.native.send_command_timing.assert_any_call(cmd)


def test_bad_config_list(asa_device):
    commands = ["crypto key generate rsa modulus 2048", "lalala"]
    results = ["ok", "Error: lalala"]

    asa_device.native.send_command_timing.side_effect = results

    with pytest.raises(asa_module.CommandListError, match=commands[1]):
        asa_device.config(commands)


def test_show(asa_device):
    command = "show running config"
    asa_device.native.send_command_timing.return_value = "interface eth1\ninspect"
    result = asa_device.show(command)
    asa_device.native.send_command_timing.assert_called_with(command)

    assert isinstance(result, str)
    assert "interface" in result
    assert "inspect" in result


def test_bad_show(asa_device):
    command = "show linux"
    asa_device.native.send_command_timing.return_value = "Error: linux"
    with pytest.raises(asa_module.CommandError):
        asa_device.show(command)


def test_show_list(asa_device):
    commands = ["show running config", "show startup-config"]
    results = ["console 0", "security-level meh"]
    asa_device.native.send_command_timing.side_effect = results

    result = asa_device.show(commands)
    assert isinstance(result, list)
    assert "console" in result[0]
    assert "security-level" in result[1]

    calls = list(mock.call(x) for x in commands)
    asa_device.native.send_command_timing.assert_has_calls(calls)


def test_bad_show_list(asa_device):
    commands = ["show badcommand", "show clock"]
    results = ["Error: badcommand", "14:31:57.089 PST Tue Feb 10 2008"]

    asa_device.native.send_command_timing.side_effect = results

    with pytest.raises(asa_module.CommandListError, match="show badcommand"):
        asa_device.show(commands)


def test_save(asa_device):
    result = asa_device.save()

    assert result
    asa_device.native.send_command_timing.assert_any_call("copy running-config startup-config")


def test_reboot(asa_device):
    asa_device.reboot()
    asa_device.native.send_command_timing.assert_any_call("reload")


def test_reboot_confirm_deprecated(asa_device):
    asa_device.reboot(confirm=True)
    asa_device.native.send_command_timing.assert_any_call("reload")


def test_boot_options_dir(asa_device):
    asa_device.native.send_command_timing.side_effect = None
    asa_device.native.send_command_timing.return_value = f"Current BOOT variable = disk0:/{BOOT_IMAGE}"
    boot_options = asa_device.boot_options
    assert boot_options == {"sys": BOOT_IMAGE}
    asa_device.native.send_command_timing.assert_called_with("show boot | i BOOT variable")


def test_boot_options_none(asa_device):
    asa_device.native.send_command_timing.side_effect = None
    asa_device.native.send_command_timing.return_value = ""
    boot_options = asa_device.boot_options
    assert boot_options["sys"] is None


def test_checkpoint(asa_device):
    asa_device.checkpoint("good_checkpoint")
    asa_device.native.send_command_timing.assert_any_call("copy running-config good_checkpoint")


def test_running_config(asa_device):
    asa_device.native.send_command_timing.return_value = "interface eth1"
    expected = asa_device.show("show running config")
    assert asa_device.running_config == expected


def test_starting_config(asa_device):
    asa_device.native.send_command_timing.return_value = "interface eth1"
    expected = asa_device.show("show startup-config")
    assert asa_device.startup_config == expected


@mock.patch.object(ASADevice, "enable")
@mock.patch.object(ASADevice, "file_copy_remote_exists", return_value=True)
def test_file_copy_already_exists(mock_file_copy_remote_exists, mock_enable, asa_device):
    asa_device._file_copy("a.txt", "a.txt", "flash:")
    mock_enable.assert_called()
    mock_file_copy_remote_exists.assert_called_once()


@mock.patch.object(ASADevice, "enable")
@mock.patch.object(ASADevice, "file_copy_remote_exists", side_effect=[False, True])
@mock.patch("pyntc.devices.asa_device.CiscoAsaFileTransfer", spec_set=asa_module.CiscoAsaFileTransfer)
@mock.patch.object(ASADevice, "_file_copy_instance")
@mock.patch.object(ASADevice, "open")
def test_file_copy_transfer_file(
    mock_open,
    mock_file_copy_instance,
    mock_cisco_asa_file_transfer,
    mock_file_copy_remote_exists,
    mock_enable,
    asa_device,
):
    args = ("a.txt", "a.txt", "flash:")
    mock_file_copy_instance.return_value = mock_cisco_asa_file_transfer
    asa_device._file_copy(*args)
    mock_enable.assert_called()
    mock_file_copy_remote_exists.assert_has_calls([mock.call(*args)] * 2)
    mock_cisco_asa_file_transfer.establish_scp_conn.assert_called_once()
    mock_cisco_asa_file_transfer.transfer_file.assert_called_once()
    mock_open.assert_not_called()
    mock_cisco_asa_file_transfer.close_scp_chan.assert_called_once()


@mock.patch.object(ASADevice, "enable")
@mock.patch.object(ASADevice, "file_copy_remote_exists", side_effect=[False, True])
@mock.patch("pyntc.devices.asa_device.CiscoAsaFileTransfer", spec_set=asa_module.CiscoAsaFileTransfer)
@mock.patch.object(ASADevice, "_file_copy_instance")
@mock.patch.object(ASADevice, "open")
def test_file_copy_transfer_file_eof_error(
    mock_open,
    mock_file_copy_instance,
    mock_cisco_asa_file_transfer,
    mock_file_copy_remote_exists,
    mock_enable,
    asa_device,
):
    args = ("a.txt", "a.txt", "flash:")
    mock_cisco_asa_file_transfer.transfer_file.side_effect = [EOFError]
    mock_file_copy_instance.return_value = mock_cisco_asa_file_transfer
    asa_device._file_copy(*args)
    mock_enable.assert_called()
    mock_file_copy_remote_exists.assert_has_calls([mock.call(*args)] * 2)
    mock_cisco_asa_file_transfer.establish_scp_conn.assert_called_once()
    mock_cisco_asa_file_transfer.transfer_file.assert_called_once()
    mock_open.assert_called()
    mock_cisco_asa_file_transfer.close_scp_chan.assert_called_once()


@mock.patch.object(ASADevice, "enable")
@mock.patch.object(ASADevice, "file_copy_remote_exists", side_effect=[False, True])
@mock.patch("pyntc.devices.asa_device.CiscoAsaFileTransfer", spec_set=asa_module.CiscoAsaFileTransfer)
@mock.patch.object(ASADevice, "_file_copy_instance")
@mock.patch.object(ASADevice, "open")
def test_file_copy_transfer_file_error(
    mock_open,
    mock_file_copy_instance,
    mock_cisco_asa_file_transfer,
    mock_file_copy_remote_exists,
    mock_enable,
    asa_device,
):
    args = ("a.txt", "a.txt", "flash:")
    mock_cisco_asa_file_transfer.establish_scp_conn.side_effect = [Exception]
    mock_file_copy_instance.return_value = mock_cisco_asa_file_transfer
    with pytest.raises(asa_module.FileTransferError):
        asa_device._file_copy(*args)
    mock_enable.assert_called()
    mock_file_copy_remote_exists.assert_called_once()
    mock_cisco_asa_file_transfer.establish_scp_conn.assert_called_once()
    mock_cisco_asa_file_transfer.transfer_file.assert_not_called()
    mock_open.assert_not_called()
    mock_cisco_asa_file_transfer.close_scp_chan.assert_called_once()


@mock.patch.object(ASADevice, "enable")
@mock.patch.object(ASADevice, "file_copy_remote_exists", return_value=False)
@mock.patch("pyntc.devices.asa_device.CiscoAsaFileTransfer", spec_set=asa_module.CiscoAsaFileTransfer)
@mock.patch.object(ASADevice, "_file_copy_instance")
@mock.patch.object(ASADevice, "open")
@mock.patch("pyntc.devices.asa_device.log.error")
def test__file_copy_transfer_file_does_not_transfer(
    mock_log,
    mock_open,
    mock_file_copy_instance,
    mock_cisco_asa_file_transfer,
    mock_file_copy_remote_exists,
    mock_enable,
    asa_device,
):
    args = ("a.txt", "a.txt", "flash:")
    mock_file_copy_instance.return_value = mock_cisco_asa_file_transfer
    with pytest.raises(asa_module.FileTransferError):
        asa_device._file_copy(*args)
    mock_enable.assert_called()
    mock_file_copy_remote_exists.assert_has_calls([mock.call(*args)] * 2)
    mock_cisco_asa_file_transfer.establish_scp_conn.assert_called_once()
    mock_cisco_asa_file_transfer.transfer_file.assert_called_once()
    mock_cisco_asa_file_transfer.close_scp_chan.assert_called_once()
    mock_log.assert_called_with(
        "Host %s: Attempted file copy, but could not validate file %s existed after transfer.", "host", "a.txt"
    )


@pytest.mark.parametrize("host,command_prefix", (("self", ""), ("peer", "failover exec mate ")), ids=("self", "peer"))
def test_get_ipv4_addresses(host, command_prefix, asa_show):
    command = "show ip address"
    device = asa_show([f"{command.replace(' ', '_')}.txt"])
    actual = device._get_ipv4_addresses(host)
    device.show.assert_called_with(f"{command_prefix}{command}")
    expected = {"inside": [ip_interface("10.1.1.1/24")], "outside": [ip_interface("10.2.2.1/27")]}
    assert actual == expected


@pytest.mark.parametrize("host,command_prefix", (("self", ""), ("peer", "failover exec mate ")), ids=("self", "peer"))
def test_get_ipv6_addresses(host, command_prefix, asa_show):
    command = "show ipv6 interface"
    device = asa_show([f"{command.replace(' ', '_')}.txt"])
    actual = device._get_ipv6_addresses(host)
    device.show.assert_called_with(f"{command_prefix}{command}")
    expected = {
        "inside": [ip_interface("2001:db8:2:3::1/64"), ip_interface("2002:db8:2:3::1/64")],
        "outside": [ip_interface("2003:db8:3:3::1/64")],
    }
    assert actual == expected


@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_wait_for_peer_reboot(mock_peer_redundancy_state, asa_device):
    mock_peer_redundancy_state.side_effect = [STANDBY_READY, FAILED, FAILED, STANDBY_READY]
    asa_device._wait_for_peer_reboot([STANDBY_READY, COLD_STANDBY], 2)
    assert mock_peer_redundancy_state.call_count == 4


@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_wait_for_peer_reboot_never_fail_error(mock_peer_redundancy_state, asa_device):
    mock_peer_redundancy_state.return_value = STANDBY_READY
    with pytest.raises(asa_module.RebootTimeoutError):
        asa_device._wait_for_peer_reboot([STANDBY_READY, COLD_STANDBY], 2)

    assert mock_peer_redundancy_state.call_count > 1


@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test__wait_for_peer_reboot_fail_state_error(mock_peer_redundancy_state, asa_device):
    mock_peer_redundancy_state.side_effect = [FAILED, FAILED, COLD_STANDBY, COLD_STANDBY]
    with pytest.raises(asa_module.RebootTimeoutError):
        asa_device._wait_for_peer_reboot([STANDBY_READY], 1)

    assert mock_peer_redundancy_state.call_count > 1


@mock.patch.object(ASADevice, "ip_address", new_callable=mock.PropertyMock, return_value=ip_address("10.1.1.1"))
@mock.patch.object(ASADevice, "ip_protocol", new_callable=mock.PropertyMock, return_value="ipv4")
@mock.patch.object(ASADevice, "ipv4_addresses", new_callable=mock.PropertyMock)
def test_connected_interface_ipv4(mock_ipv4_addresses, mock_ip_protocol, mock_ip_address, asa_device):
    mock_ipv4_addresses.return_value = {
        "outside": [ip_interface("10.2.2.2/24")],
        "management": [ip_interface("10.1.1.1/23")],
    }
    actual = asa_device.connected_interface
    assert actual == "management"
    mock_ipv4_addresses.assert_called_once()


@mock.patch.object(ASADevice, "ip_address", new_callable=mock.PropertyMock, return_value=ip_address("2002:db8:2:3::1"))
@mock.patch.object(ASADevice, "ip_protocol", new_callable=mock.PropertyMock, return_value="ipv6")
@mock.patch.object(ASADevice, "ipv6_addresses", new_callable=mock.PropertyMock)
def test_connected_interface_ipv6(mock_ipv6_addresses, mock_ip_protocol, mock_ip_address, asa_device):
    mock_ipv6_addresses.return_value = {
        "outside": [ip_interface("2001:db8:2:3::1/64"), ip_interface("2002:db8:2:3::1/64")],
        "management": [ip_interface("2003:db8:2:3::1/64")],
    }
    actual = asa_device.connected_interface
    assert actual == "outside"
    mock_ipv6_addresses.assert_called_once()


@mock.patch.object(ASADevice, "is_active", return_value=True)
@mock.patch.object(ASADevice, "peer_device")
@mock.patch.object(ASADevice, "config")
@mock.patch.object(ASADevice, "save")
def test_enable_scp_active_device(mock_save, mock_config, mock_peer_device, mock_is_active, asa_device):
    asa_device.enable_scp()
    mock_is_active.assert_has_calls([mock.call()] * 2)
    mock_peer_device.assert_not_called()
    mock_config.assert_called_with("ssh scopy enable")
    mock_save.assert_called()


@mock.patch.object(ASADevice, "is_active", side_effect=[False, True])
@mock.patch.object(ASADevice, "peer_device", new_callable=mock.PropertyMock)
@mock.patch.object(ASADevice, "config")
@mock.patch.object(ASADevice, "save")
def test_enable_scp_standby_device(mock_save, mock_config, mock_peer_device, mock_is_active, asa_device):
    mock_peer_device.return_value = asa_device
    asa_device.enable_scp()
    mock_is_active.assert_has_calls([mock.call()] * 2)
    mock_peer_device.assert_called()
    mock_config.assert_called_with("ssh scopy enable")
    mock_save.assert_called()


@mock.patch.object(ASADevice, "is_active", return_value=False)
@mock.patch.object(ASADevice, "peer_device", new_callable=mock.PropertyMock)
@mock.patch.object(ASADevice, "config")
@mock.patch.object(ASADevice, "save")
@mock.patch("pyntc.devices.asa_device.log.error")
def test_enable_scp_device_not_active(mock_log, mock_save, mock_config, mock_peer_device, mock_is_active, asa_device):
    mock_peer_device.return_value = asa_device
    with pytest.raises(asa_module.FileTransferError):
        asa_device.enable_scp()
    mock_log.assert_called_once_with("Host %s: Unable to establish a connection with the active device", "host")
    mock_is_active.assert_has_calls([mock.call()] * 2)
    mock_peer_device.assert_called()
    mock_config.assert_not_called()
    mock_save.assert_not_called()


@mock.patch.object(ASADevice, "is_active", return_value=True)
@mock.patch.object(ASADevice, "peer_device")
@mock.patch.object(
    ASADevice, "config", side_effect=[asa_module.CommandError(command="ssh scopy enable", message="Error")]
)
@mock.patch.object(ASADevice, "save")
@mock.patch("pyntc.devices.asa_device.log.error")
def test_enable_scp_enable_fail(mock_log, mock_save, mock_config, mock_peer_device, mock_is_active, asa_device):
    with pytest.raises(asa_module.FileTransferError):
        asa_device.enable_scp()
    mock_log.assert_called_once_with("Host %s: Unable to enable scopy on the device", "host")
    mock_config.assert_called_with("ssh scopy enable")
    mock_save.assert_not_called()


@mock.patch("pyntc.devices.asa_device.os.path.getsize", return_value=1024)
@mock.patch.object(ASADevice, "_check_free_space")
@mock.patch.object(os.path, "basename", return_value="a.txt")
@mock.patch.object(ASADevice, "_get_file_system", return_value="flash:")
@mock.patch.object(ASADevice, "enable_scp")
@mock.patch.object(ASADevice, "_file_copy")
def test_file_copy_no_peer_no_args(
    mock_file_copy, mock_enable_scp, mock_get_file_system, mock_basename, _check_space, _getsize, asa_device
):
    asa_device.file_copy("path/to/a.txt")
    mock_basename.assert_called()
    mock_get_file_system.assert_called()
    mock_enable_scp.assert_called()
    mock_file_copy.assert_called_once()
    mock_file_copy.assert_called_with("path/to/a.txt", "a.txt", "flash:")


@mock.patch("pyntc.devices.asa_device.os.path.getsize", return_value=1024)
@mock.patch.object(ASADevice, "_check_free_space")
@mock.patch.object(os.path, "basename")
@mock.patch.object(ASADevice, "_get_file_system")
@mock.patch.object(ASADevice, "enable_scp")
@mock.patch.object(ASADevice, "_file_copy")
def test_file_copy_no_peer_pass_args(
    mock_file_copy, mock_enable_scp, mock_get_file_system, mock_basename, _check_space, _getsize, asa_device
):
    args = ("path/to/a.txt", "b.txt", "bootflash:")
    asa_device.file_copy(*args)
    mock_basename.assert_not_called()
    mock_get_file_system.assert_not_called()
    mock_enable_scp.assert_called()
    mock_file_copy.assert_called_once()
    mock_file_copy.assert_called_with(*args)


@mock.patch("pyntc.devices.asa_device.os.path.getsize", return_value=1024)
@mock.patch.object(ASADevice, "_check_free_space")
@mock.patch.object(os.path, "basename")
@mock.patch.object(ASADevice, "_get_file_system")
@mock.patch.object(ASADevice, "enable_scp")
@mock.patch.object(ASADevice, "_file_copy")
@mock.patch.object(ASADevice, "peer_device")
def test_file_copy_include_peer(
    mock_peer_device,
    mock_file_copy,
    mock_enable_scp,
    mock_get_file_system,
    mock_basename,
    _check_space,
    _getsize,
    asa_device,
):
    mock_peer_device.return_value = asa_device
    args = ("path/to/a.txt", "a.txt", "flash:")
    asa_device.file_copy(*args, peer=True)
    mock_basename.assert_not_called()
    mock_get_file_system.assert_not_called()
    mock_enable_scp.assert_called_once()
    mock_file_copy.assert_called_with(*args)
    mock_peer_device._file_copy.assert_called_with(*args)


@mock.patch("pyntc.devices.asa_device.ConnectHandler")
@pytest.mark.parametrize("ip", ("10.1.1.1", "2001:db8:2:3::1"), ids=("ipv4", "ipv6"))
def test_ip_address_from_ip(mock_connect_handler, ip, asa_device):
    device = ASADevice(ip, "username", "password")
    actual = device.ip_address
    expected = ip_address(ip)
    assert actual == expected
    device.native.remote_conn.transport.getpeername.assert_not_called()


def test_ip_address_from_hostname(asa_device):
    with mock.patch.object(asa_device.native.remote_conn.transport, "getpeername") as mock_getpeername:
        mock_getpeername.return_value = ("10.1.1.1", None)
        actual = asa_device.ip_address
    expected = ip_address("10.1.1.1")
    assert actual == expected
    asa_device.native.remote_conn.transport.getpeername.assert_not_called()


@mock.patch.object(ASADevice, "_get_ipv4_addresses")
def test_ipv4_addresses(mock_get_ipv4_addresses, asa_device):
    expected = {"outside": [ip_interface("10.132.8.6/24")], "inside": [ip_interface("10.1.1.2/23")]}
    mock_get_ipv4_addresses.return_value = expected
    actual = asa_device.ipv4_addresses
    assert actual == expected
    mock_get_ipv4_addresses.assert_called_with("self")


@mock.patch.object(ASADevice, "_get_ipv6_addresses")
def test_ipv6_addresses(mock_get_ipv6_addresses, asa_device):
    expected = {"outside": [ip_interface("fe80::5200:ff:fe0a:1/64")]}
    mock_get_ipv6_addresses.return_value = expected
    actual = asa_device.ipv6_addresses
    assert actual == expected
    mock_get_ipv6_addresses.assert_called_with("self")


@mock.patch.object(ASADevice, "ip_address", new_callable=mock.PropertyMock)
@pytest.mark.parametrize("ip,ip_version", (("10.1.1.1", "4"), ("fe80::5200:ff:fe0a:1", "6")), ids=("ipv4", "ipv6"))
def test_ip_protocol(mock_ip_address, ip, ip_version, asa_device):
    mock_ip_address.return_value = ip_address(ip)
    actual = asa_device.ip_protocol

    assert actual == f"ipv{ip_version}"


@mock.patch.object(ASADevice, "redundancy_state", new_callable=mock.PropertyMock)
@pytest.mark.parametrize(
    "redundancy_state,expected",
    (
        (ACTIVE, True),
        (STANDBY_READY, False),
        (NEGOTIATION, False),
        (FAILED, False),
        (COLD_STANDBY, False),
        (None, True),
        ("disabled", True),
    ),
    ids=(ACTIVE, "standby_ready", NEGOTIATION, FAILED, "cold_standby", "unsupported", "disabled"),
)
def test_is_active(mock_redundancy_state, asa_device, redundancy_state, expected):
    mock_redundancy_state.return_value = redundancy_state
    actual = asa_device.is_active()
    assert actual is expected


@mock.patch.object(ASADevice, "peer_ip_address", new_callable=mock.PropertyMock, return_value="10.1.1.2")
@mock.patch.object(ASADevice, "__init__", return_value=None)
def test_peer_device(mock_init, mock_peer_ip_address, asa_device):
    assert asa_device._peer_device is None
    peer_device = asa_device.peer_device
    assert isinstance(peer_device, ASADevice)
    assert peer_device == asa_device._peer_device
    mock_init.assert_called_with(
        "10.1.1.2", asa_device.username, asa_device.password, asa_device.secret, asa_device.port, **asa_device.kwargs
    )


@mock.patch.object(ASADevice, "peer_ip_address")
@mock.patch.object(ASADevice, "__init__", return_value=None)
@mock.patch.object(ASADevice, "open")
def test_peer_device_already_exists(mock_open, mock_init, mock_peer_ip_address, asa_device):
    asa_device._peer_device = asa_device
    assert asa_device._peer_device is not None
    peer_device = asa_device.peer_device
    assert isinstance(peer_device, ASADevice)
    assert peer_device == asa_device._peer_device
    mock_init.assert_not_called()
    mock_open.assert_called()


@mock.patch.object(ASADevice, "ip_address", new_callable=mock.PropertyMock)
@mock.patch.object(ASADevice, "ip_protocol", new_callable=mock.PropertyMock)
@mock.patch.object(ASADevice, "connected_interface", new_callable=mock.PropertyMock, return_value="mgmt")
@pytest.mark.parametrize(
    "ip,ip_version,peer_addresses",
    (
        (
            "10.3.3.2",
            "4",
            {
                "outside": [ip_interface("10.1.1.2/24")],
                "inside": [ip_interface("10.2.2.2/24")],
                "mgmt": [ip_interface("10.3.3.2/24")],
            },
        ),
        (
            "2003:db8:2:3::2",
            "6",
            {
                "outside": [ip_interface("2001:db8:2:3::2/64")],
                "inside": [ip_interface("2002:db8:2:3::2/64")],
                "mgmt": [ip_interface("2003:db8:2:3::2/64")],
            },
        ),
    ),
    ids=("ipv4", "ipv6"),
)
def test_peer_ip_address(
    mock_connected_interface, mock_ip_protocol, mock_ip_address, ip, ip_version, peer_addresses, asa_device
):
    mock_ip_address.return_value = ip_address(ip)
    mock_ip_protocol.return_value = f"ipv{ip_version}"
    with mock.patch.object(
        ASADevice, f"peer_ipv{ip_version}_addresses", new_callable=mock.PropertyMock
    ) as mock_peer_addresses:
        mock_peer_addresses.return_value = peer_addresses
        actual = asa_device.peer_ip_address

    assert actual == peer_addresses["mgmt"][0].ip


@mock.patch.object(ASADevice, "_get_ipv4_addresses")
def test_peer_ipv4_addresses(mock_get_ipv4_addresses, asa_device):
    expected = {"outside": [ip_interface("10.132.8.7/24")], "inside": [ip_interface("10.1.1.3/23")]}
    mock_get_ipv4_addresses.return_value = expected
    actual = asa_device.peer_ipv4_addresses
    assert actual == expected
    mock_get_ipv4_addresses.assert_called_with("peer")


@mock.patch.object(ASADevice, "_get_ipv6_addresses")
def test_peer_ipv6_addresses(mock_get_ipv6_addresses, asa_device):
    expected = {"outside": [ip_interface("fe80::5200:ff:fe0a:2/64")]}
    mock_get_ipv6_addresses.return_value = expected
    actual = asa_device.peer_ipv6_addresses
    assert actual == expected
    mock_get_ipv6_addresses.assert_called_with("peer")


@pytest.mark.parametrize(
    "side_effect,expected",
    (
        ("show_failover_host_active.txt", STANDBY_READY),
        ("show_failover_host_standby.txt", ACTIVE),
        ("show_failover_host_off.txt", "disabled"),
        ("show_failover_groups_active_active.txt", ACTIVE),
        ("show_failover_groups_active_standby.txt", STANDBY_READY),
        ("show_failover_groups_standby_active.txt", ACTIVE),
        ("show_failover_peer_cold.txt", COLD_STANDBY),
        ("show_failover_peer_failed.txt", FAILED),
        ("show_failover_peer_not_detected.txt", NOT_DETECTED),
        (asa_module.CommandError("show failover", r"% invalid command"), None),
    ),
    ids=(
        "standby",
        ACTIVE,
        "disabled",
        "active_active",
        "active_standby",
        "standby_active",
        COLD_STANDBY,
        FAILED,
        NOT_DETECTED,
        "none",
    ),
)
def test_peer_redundancy_state(side_effect, expected, asa_show):
    device = asa_show([side_effect])
    actual = device.peer_redundancy_state
    assert actual == expected


@mock.patch.object(ASADevice, "_wait_for_peer_reboot")
@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_reboot_standby(mock_peer_redundancy_state, mock_wait_for_peer_reboot, asa_show):
    mock_peer_redundancy_state.return_value = STANDBY_READY
    device = asa_show([""])
    assert device.reboot_standby() is None
    mock_peer_redundancy_state.assert_called_once()
    mock_wait_for_peer_reboot.assert_called_with(acceptable_states=[STANDBY_READY])


@mock.patch.object(ASADevice, "_wait_for_peer_reboot")
@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_reboot_standby_pass_args(mock_peer_redundancy_state, mock_wait_for_peer_reboot, asa_show):
    device = asa_show([""])
    device.reboot_standby(acceptable_states=[COLD_STANDBY, STANDBY_READY], timeout=1)
    mock_peer_redundancy_state.assert_not_called()
    mock_wait_for_peer_reboot.assert_called_with(acceptable_states=[COLD_STANDBY, STANDBY_READY], timeout=1)


@mock.patch.object(ASADevice, "_wait_for_peer_reboot")
def test_reboot_standby_error(mock_wait_for_peer_reboot, asa_show):
    device = asa_show([""])
    mock_wait_for_peer_reboot.side_effect = [asa_module.RebootTimeoutError(device.host, 1)]
    with pytest.raises(asa_module.RebootTimeoutError):
        device.reboot_standby(acceptable_states=[STANDBY_READY], timeout=1)

    mock_wait_for_peer_reboot.assert_called()


@pytest.mark.parametrize(
    "side_effect,expected",
    (
        ("show_failover_host_active.txt", "on"),
        ("show_failover_host_off.txt", "off"),
        (asa_module.CommandError("show failover", r"% invalid command"), "n/a"),
    ),
    ids=("on", "off", "n/a"),
)
def test_redundancy_mode(side_effect, expected, asa_show):
    device = asa_show([side_effect])
    actual = device.redundancy_mode
    assert actual == expected


@pytest.mark.parametrize(
    "side_effect,expected",
    (
        ("show_failover_host_active.txt", ACTIVE),
        ("show_failover_host_standby.txt", STANDBY_READY),
        ("show_failover_host_off.txt", "disabled"),
        ("show_failover_host_negotiation.txt", NEGOTIATION),
        ("show_failover_groups_active_active.txt", ACTIVE),
        ("show_failover_groups_active_standby.txt", ACTIVE),
        ("show_failover_groups_standby_active.txt", STANDBY_READY),
        (asa_module.CommandError("show failover", r"% invalid command"), None),
    ),
    ids=(ACTIVE, "standby", "disabled", NEGOTIATION, "active_active", "active_standby", "standby_active", "none"),
)
def test_redundancy_state(side_effect, expected, asa_show):
    device = asa_show([side_effect])
    actual = device.redundancy_state
    assert actual == expected


def test_send_command_timing(asa_send_command_timing):
    command = "send_command_timing"
    device = asa_send_command_timing([f"{command}.txt"])
    device._send_command(command)
    device.native.send_command_timing.assert_called()
    device.native.send_command_timing.assert_called_with(command)


def test_send_command_expect(asa_send_command):
    command = "send_command_expect"
    device = asa_send_command([f"{command}.txt"])
    device._send_command(command, expect_string="Continue?")
    device.native.send_command.assert_called_with("send_command_expect", expect_string="Continue?")


def test_send_command_error(asa_send_command_timing):
    command = "send_command_error"
    device = asa_send_command_timing([f"{command}.txt"])
    with pytest.raises(asa_module.CommandError):
        device._send_command(command)
    device.native.send_command_timing.assert_called()


@mock.patch.object(ASADevice, "_raw_version_data", autospec=True)
def test_uptime(mock_raw_version_data, asa_device):
    mock_raw_version_data.return_value = VERSION_DATA
    uptime = asa_device.uptime
    assert uptime == 7620


@mock.patch.object(ASADevice, "_raw_version_data", autospec=True)
def test_uptime_string(mock_raw_version_data, asa_device):
    mock_raw_version_data.return_value = VERSION_DATA
    uptime_string = asa_device.uptime_string
    assert uptime_string == "00:02:07:00"


@mock.patch.object(ASADevice, "_raw_version_data", autospec=True)
def test_model(mock_raw_version_data, asa_device):
    mock_raw_version_data.return_value = VERSION_DATA
    model = asa_device.model
    assert model == "ASAv, 2048 MB RAM, CPU Lynnfield 3695 MHz"


@mock.patch.object(ASADevice, "_raw_version_data", autospec=True)
def test_os_version(mock_raw_version_data, asa_device):
    mock_raw_version_data.return_value = VERSION_DATA
    os_version = asa_device.os_version
    assert os_version == "9.16(2)"


@mock.patch.object(ASADevice, "_raw_version_data", autospec=True)
def test_serial_number(mock_raw_version_data, asa_device):
    mock_raw_version_data.return_value = VERSION_DATA
    sn = asa_device.serial_number
    assert sn == "9ANMLKTFC5B"


@mock.patch.object(ASADevice, "_interfaces_detailed_list", autospec=True)
def test_interfaces(mock_get_intf_list, asa_device):
    expected = [{"interface": "Management0/0"}, {"interface": "GigabitEthernet0/0"}]
    mock_get_intf_list.return_value = expected
    interfaces = asa_device.interfaces
    assert interfaces == ["Management0/0", "GigabitEthernet0/0"]


@mock.patch.object(ASADevice, "_show_vlan", autospec=True)
def test_vlan(mock_get_vlans, asa_device):
    expected = [10, 20]
    mock_get_vlans.return_value = expected
    vlans = asa_device.vlans
    assert vlans == [10, 20]


@mock.patch.object(ASADevice, "open")
def test_port_none(patch):
    device = ASADevice("host", "user", "pass", port=None)
    assert device.port == 22


# ---------------------------------------------------------------------------
# check_file_exists tests
# ---------------------------------------------------------------------------


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
def test_check_file_exists_returns_true(mock_fs, asa_device):
    asa_device.native.send_command.return_value = "     -rwx  94038  Apr 13 2026 14:25  asa.bin\n"
    result = asa_device.check_file_exists("asa.bin")
    assert result is True
    asa_device.native.send_command.assert_called_with("dir disk0:asa.bin", read_timeout=30)


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
def test_check_file_exists_returns_false(mock_fs, asa_device):
    asa_device.native.send_command.return_value = "ERROR: disk0:/asa.bin: No such file or directory"
    result = asa_device.check_file_exists("asa.bin")
    assert result is False


@mock.patch.object(ASADevice, "_get_file_system")
def test_check_file_exists_uses_provided_file_system(mock_fs, asa_device):
    asa_device.native.send_command.return_value = "     -rwx  94038  Apr 13 2026 14:25  asa.bin\n"
    result = asa_device.check_file_exists("asa.bin", file_system="flash:")
    assert result is True
    asa_device.native.send_command.assert_called_with("dir flash:asa.bin", read_timeout=30)
    mock_fs.assert_not_called()


# ---------------------------------------------------------------------------
# get_remote_checksum tests
# ---------------------------------------------------------------------------

MD5_CHECKSUM = "aabbccdd11223344aabbccdd11223344"
SHA512_CHECKSUM = "90368777ae062ae6989272db08fa6c624601f841da5825b8ff1faaccd2c98b19ea4ca5"


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
def test_get_remote_checksum_md5(mock_fs, asa_device):
    asa_device.native.send_command_timing.return_value = (
        f"!!!!!!!!!!!!!!!!!!!!!!!!Done!\nverify /MD5 (disk0:/asa.bin) = {MD5_CHECKSUM}"
    )
    result = asa_device.get_remote_checksum("asa.bin")
    assert result == MD5_CHECKSUM
    asa_device.native.send_command_timing.assert_called_with("verify /md5 disk0:asa.bin", read_timeout=300)


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
def test_get_remote_checksum_sha512(mock_fs, asa_device):
    asa_device.native.send_command_timing.return_value = (
        f"!!!!!!!!!!!!!!!!!!!!!!!!Done!\nverify /SHA-512 (disk0:/asa.bin) = {SHA512_CHECKSUM}"
    )
    result = asa_device.get_remote_checksum("asa.bin", hashing_algorithm="sha512")
    assert result == SHA512_CHECKSUM
    asa_device.native.send_command_timing.assert_called_with("verify /sha-512 disk0:asa.bin", read_timeout=300)


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
def test_get_remote_checksum_uses_provided_file_system(mock_fs, asa_device):
    asa_device.native.send_command_timing.return_value = (
        f"!!!!!!!!!!!!!!!!!!!!!!!!Done!\nverify /MD5 (flash:/asa.bin) = {MD5_CHECKSUM}"
    )
    result = asa_device.get_remote_checksum("asa.bin", file_system="flash:")
    assert result == MD5_CHECKSUM
    asa_device.native.send_command_timing.assert_called_with("verify /md5 flash:asa.bin", read_timeout=300)
    mock_fs.assert_not_called()


def test_get_remote_checksum_invalid_algorithm(asa_device):
    with pytest.raises(ValueError, match="hashing_algorithm must be"):
        asa_device.get_remote_checksum("asa.bin", hashing_algorithm="sha256")


# ---------------------------------------------------------------------------
# verify_file tests
# ---------------------------------------------------------------------------


@mock.patch.object(ASADevice, "compare_file_checksum", return_value=True)
@mock.patch.object(ASADevice, "check_file_exists", return_value=True)
def test_verify_file_returns_true(mock_exists, mock_checksum, asa_device):
    result = asa_device.verify_file(MD5_CHECKSUM, "asa.bin")
    assert result is True
    mock_exists.assert_called_once_with("asa.bin")
    mock_checksum.assert_called_once_with(MD5_CHECKSUM, "asa.bin", "md5")


@mock.patch.object(ASADevice, "check_file_exists", return_value=False)
def test_verify_file_returns_false_not_exists(mock_exists, asa_device):
    result = asa_device.verify_file(MD5_CHECKSUM, "asa.bin")
    assert result is False
    mock_exists.assert_called_once_with("asa.bin")


@mock.patch.object(ASADevice, "compare_file_checksum", return_value=False)
@mock.patch.object(ASADevice, "check_file_exists", return_value=True)
def test_verify_file_returns_false_checksum_mismatch(mock_exists, mock_checksum, asa_device):
    result = asa_device.verify_file("wrongchecksum", "asa.bin")
    assert result is False


# ---------------------------------------------------------------------------
# remote_file_copy tests
# ---------------------------------------------------------------------------

FILE_COPY_MODEL_FTP = FileCopyModel(
    download_url="ftp://example-user:example-password@192.0.2.1/asa.bin",
    checksum=SHA512_CHECKSUM,
    file_name="asa.bin",
    hashing_algorithm="sha512",
    timeout=900,
)
FILE_COPY_MODEL_TFTP = FileCopyModel(
    download_url="tftp://192.0.2.1/asa.bin",
    checksum=SHA512_CHECKSUM,
    file_name="asa.bin",
    hashing_algorithm="sha512",
    timeout=900,
)
FILE_COPY_MODEL_SCP = FileCopyModel(
    download_url="scp://example-user:example-password@192.0.2.1/asa.bin",
    checksum=SHA512_CHECKSUM,
    file_name="asa.bin",
    hashing_algorithm="sha512",
    timeout=900,
)
FILE_COPY_MODEL_HTTP = FileCopyModel(
    download_url="http://example-user:example-password@192.0.2.1/asa.bin",
    checksum=SHA512_CHECKSUM,
    file_name="asa.bin",
    hashing_algorithm="sha512",
    timeout=900,
)
FILE_COPY_MODEL_HTTPS = FileCopyModel(
    download_url="https://example-user:example-password@192.0.2.1/asa.bin",
    checksum=SHA512_CHECKSUM,
    file_name="asa.bin",
    hashing_algorithm="sha512",
    timeout=900,
)


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file")
def test_remote_file_copy_type_error(mock_verify, mock_fs, asa_device):
    with pytest.raises(TypeError):
        asa_device.remote_file_copy("not_a_file_copy_model")


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", return_value=True)
def test_remote_file_copy_already_exists(mock_verify, mock_fs, asa_device):
    asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)
    # verify_file is called once (pre-check passes); post-check is skipped since no copy was needed
    assert mock_verify.call_count == 1
    mock_verify.assert_any_call(SHA512_CHECKSUM, "asa.bin", hashing_algorithm="sha512", file_system="disk0:")
    asa_device.native.send_command.assert_not_called()


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_success(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Address or name of remote host [192.0.2.1]?",
        "Source username [example-user]?",
        "Source filename [asa.bin]?",
        "Destination filename [asa.bin]?",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)
    assert mock_verify.call_count == 2
    asa_device.native.send_command.assert_any_call(
        "copy ftp://192.0.2.1/asa.bin disk0:asa.bin",
        expect_string=mock.ANY,
        read_timeout=900,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_no_dest_defaults_to_file_name(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)
    asa_device.native.send_command.assert_any_call(
        "copy ftp://192.0.2.1/asa.bin disk0:asa.bin",
        expect_string=mock.ANY,
        read_timeout=900,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_uses_provided_file_system(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_FTP, file_system="flash:")
    mock_fs.assert_not_called()
    asa_device.native.send_command.assert_any_call(
        "copy ftp://192.0.2.1/asa.bin flash:asa.bin",
        expect_string=mock.ANY,
        read_timeout=900,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", return_value=False)
def test_remote_file_copy_error_in_output(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.return_value = "%Error opening ftp://192.0.2.1/asa.bin (Timed out)"
    with pytest.raises(FileTransferError):
        asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, False])
def test_remote_file_copy_verify_fails_after_copy(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    with pytest.raises(FileTransferError):
        asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)
    assert mock_verify.call_count == 2


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", return_value=False)
def test_remote_file_copy_unmatched_output_raises(mock_verify, mock_fs, asa_device):
    """Unexpected output that matches no known prompt or success/error pattern raises FileTransferError."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.return_value = "!!!!!!!!!! some unexpected banner line !!!!!!!!!!"
    with pytest.raises(FileTransferError):
        asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_password_prompt_uses_cmd_verify_false(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Password:",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)
    # The password response must be sent with cmd_verify=False
    asa_device.native.send_command.assert_any_call(
        FILE_COPY_MODEL_FTP.token,
        expect_string=mock.ANY,
        read_timeout=900,
        cmd_verify=False,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_confirm_prompt_uses_cmd_verify_true(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Address or name of remote host [192.0.2.1]?",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)
    asa_device.native.send_command.assert_any_call(
        "",
        expect_string=mock.ANY,
        read_timeout=900,
        cmd_verify=True,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_clean_url_used_in_command(mock_verify, mock_fs, asa_device):
    """Credentials must be stripped from the copy command (clean_url used, not download_url)."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_FTP)
    # clean_url strips credentials; raw download_url should NOT appear in the command
    call_args = asa_device.native.send_command.call_args_list[0][0][0]
    assert "example-user:example-password" not in call_args
    assert "ftp://192.0.2.1/asa.bin" in call_args


# ---------------------------------------------------------------------------
# remote_file_copy TFTP tests
# ---------------------------------------------------------------------------


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_tftp_success(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_TFTP)
    assert mock_verify.call_count == 2
    asa_device.native.send_command.assert_any_call(
        "copy tftp://192.0.2.1/asa.bin disk0:asa.bin",
        expect_string=mock.ANY,
        read_timeout=900,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_tftp_interactive_prompts(mock_verify, mock_fs, asa_device):
    """TFTP has no credentials; confirmation prompts are answered with empty string."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Address or name of remote host [192.0.2.1]?",
        "Source filename [asa.bin]?",
        "Destination filename [asa.bin]?",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_TFTP)
    asa_device.native.send_command.assert_any_call(
        "",
        expect_string=mock.ANY,
        read_timeout=900,
        cmd_verify=True,
    )


# ---------------------------------------------------------------------------
# remote_file_copy SCP tests
# ---------------------------------------------------------------------------


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_scp_success(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_SCP)
    assert mock_verify.call_count == 2
    asa_device.native.send_command.assert_any_call(
        "copy scp://192.0.2.1/asa.bin disk0:asa.bin",
        expect_string=mock.ANY,
        read_timeout=900,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_scp_ssh_host_key_prompt(mock_verify, mock_fs, asa_device):
    """SCP SSH host-key verification prompt is answered with 'yes' and cmd_verify=True."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Are you sure you want to continue connecting (yes/no)?",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_SCP)
    asa_device.native.send_command.assert_any_call(
        "yes",
        expect_string=mock.ANY,
        read_timeout=900,
        cmd_verify=True,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_scp_password_prompt(mock_verify, mock_fs, asa_device):
    """SCP password prompt sends token with cmd_verify=False."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Password:",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_SCP)
    asa_device.native.send_command.assert_any_call(
        FILE_COPY_MODEL_SCP.token,
        expect_string=mock.ANY,
        read_timeout=900,
        cmd_verify=False,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_scp_clean_url_used_in_command(mock_verify, mock_fs, asa_device):
    """Credentials must be stripped from the SCP copy command."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_SCP)
    call_args = asa_device.native.send_command.call_args_list[0][0][0]
    assert "example-user:example-password" not in call_args
    assert "scp://192.0.2.1/asa.bin" in call_args


# ---------------------------------------------------------------------------
# remote_file_copy HTTP tests
# ---------------------------------------------------------------------------


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_http_success(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_HTTP)
    assert mock_verify.call_count == 2
    asa_device.native.send_command.assert_any_call(
        "copy http://192.0.2.1/asa.bin disk0:asa.bin",
        expect_string=mock.ANY,
        read_timeout=900,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_http_password_prompt(mock_verify, mock_fs, asa_device):
    """HTTP password prompt sends token with cmd_verify=False."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Password:",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_HTTP)
    asa_device.native.send_command.assert_any_call(
        FILE_COPY_MODEL_HTTP.token,
        expect_string=mock.ANY,
        read_timeout=900,
        cmd_verify=False,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_http_clean_url_used_in_command(mock_verify, mock_fs, asa_device):
    """Credentials must be stripped from the HTTP copy command."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_HTTP)
    call_args = asa_device.native.send_command.call_args_list[0][0][0]
    assert "example-user:example-password" not in call_args
    assert "http://192.0.2.1/asa.bin" in call_args


# ---------------------------------------------------------------------------
# remote_file_copy HTTPS tests
# ---------------------------------------------------------------------------


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_https_success(mock_verify, mock_fs, asa_device):
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_HTTPS)
    assert mock_verify.call_count == 2
    asa_device.native.send_command.assert_any_call(
        "copy https://192.0.2.1/asa.bin disk0:asa.bin",
        expect_string=mock.ANY,
        read_timeout=900,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_https_password_prompt(mock_verify, mock_fs, asa_device):
    """HTTPS password prompt sends token with cmd_verify=False."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "Password:",
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_HTTPS)
    asa_device.native.send_command.assert_any_call(
        FILE_COPY_MODEL_HTTPS.token,
        expect_string=mock.ANY,
        read_timeout=900,
        cmd_verify=False,
    )


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_https_clean_url_used_in_command(mock_verify, mock_fs, asa_device):
    """Credentials must be stripped from the HTTPS copy command."""
    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]
    asa_device.remote_file_copy(FILE_COPY_MODEL_HTTPS)
    call_args = asa_device.native.send_command.call_args_list[0][0][0]
    assert "example-user:example-password" not in call_args
    assert "https://192.0.2.1/asa.bin" in call_args


# ---------------------------------------------------------------------------
# Pre-transfer free-space tests (NAPPS-1087)
# ---------------------------------------------------------------------------

DIR_OUTPUT_WITH_TRAILER = (
    "Directory of disk0:/\n\n"
    "1  -rw-    15183868                asa9-12-3-11-smp-k8.bin\n\n"
    "16777216 bytes total (1592488 bytes free)"
)


@mock.patch.object(ASADevice, "show", return_value=DIR_OUTPUT_WITH_TRAILER)
def test_get_free_space_parses_dir_trailer(_mock_show, asa_device):
    """_get_free_space returns the bytes-free value from the dir trailer."""
    assert asa_device._get_free_space() == 1592488


@mock.patch.object(ASADevice, "show", return_value="Directory of disk0:/\nno trailer here")
def test_get_free_space_raises_when_trailer_missing(_mock_show, asa_device):
    """_get_free_space raises CommandError when the trailer can't be parsed."""
    with pytest.raises(CommandError):
        asa_device._get_free_space()


@mock.patch("pyntc.devices.asa_device.os.path.getsize", return_value=10**12)
@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "show", return_value=DIR_OUTPUT_WITH_TRAILER)
@mock.patch.object(ASADevice, "enable_scp")
@mock.patch.object(ASADevice, "_file_copy")
def test_file_copy_raises_not_enough_free_space(mock_file_copy, mock_enable_scp, _show, _fs, _getsize, asa_device):
    """file_copy raises NotEnoughFreeSpaceError and never runs SCP transfer."""
    with pytest.raises(NotEnoughFreeSpaceError):
        asa_device.file_copy("path/to/image.bin")

    mock_enable_scp.assert_not_called()
    mock_file_copy.assert_not_called()


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "verify_file", return_value=False)
@mock.patch.object(ASADevice, "show", return_value=DIR_OUTPUT_WITH_TRAILER)
def test_remote_file_copy_raises_not_enough_free_space(_show, _verify, _fs, asa_device):
    """remote_file_copy raises NotEnoughFreeSpaceError and never issues a copy command."""
    oversized = FileCopyModel(
        download_url="ftp://192.0.2.1/asa.bin",
        checksum=SHA512_CHECKSUM,
        file_name="asa.bin",
        file_size=2,
        file_size_unit="gigabytes",
        hashing_algorithm="sha512",
    )

    with pytest.raises(NotEnoughFreeSpaceError):
        asa_device.remote_file_copy(oversized)

    asa_device.native.send_command.assert_not_called()


@mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
@mock.patch.object(ASADevice, "_check_free_space")
@mock.patch.object(ASADevice, "verify_file", side_effect=[False, True])
def test_remote_file_copy_skips_space_check_when_file_size_omitted(mock_verify, mock_check, _fs, asa_device):
    """When FileCopyModel has no file_size, _check_free_space is NOT called."""
    model = FileCopyModel(
        download_url="ftp://192.0.2.1/asa.bin",
        checksum=SHA512_CHECKSUM,
        file_name="asa.bin",
        hashing_algorithm="sha512",
    )  # file_size intentionally omitted
    assert model.file_size_bytes is None

    asa_device.native.find_prompt.return_value = "asa5512#"
    asa_device.native.send_command.side_effect = [
        "94038 bytes copied in 0.90 secs",
    ]

    asa_device.remote_file_copy(model)

    mock_check.assert_not_called()
    asa_device.native.send_command.assert_called()  # transfer still happens
