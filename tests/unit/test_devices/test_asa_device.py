import os
from ipaddress import ip_address, ip_interface
from unittest import mock

import pytest
from pyntc.devices import asa_device as asa_module
from pyntc.devices import ASADevice

from .device_mocks.asa import send_command

BOOT_IMAGE = "asa9-12-3-12-smp-k8.bin"
BOOT_OPTIONS_PATH = "pyntc.devices.asa_device.ASADevice.boot_options"
ACTIVE = "active"
STANDBY_READY = "standby ready"
NEGOTIATION = "negotiation"
FAILED = "failed"
NOT_DETECTED = "not detected"
COLD_STANDBY = "cold standby"


class TestASADevice:
    def setup(self, api):
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

    def teardown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()
        self.count_teardown += 1

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
    @mock.patch.object(ASADevice, "config_list", return_value=None)
    def test_set_boot_options(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
            mock_cl.assert_called_with([f"boot system disk0:/{BOOT_IMAGE}"])

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    @mock.patch.object(ASADevice, "config_list", return_value=None)
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
    @mock.patch.object(ASADevice, "config_list", return_value=None)
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
    asa_device.config_list(commands)

    for cmd in commands:
        asa_device.native.send_command_timing.assert_any_call(cmd)


def test_bad_config_list(asa_device):
    commands = ["crypto key generate rsa modulus 2048", "lalala"]
    results = ["ok", "Error: lalala"]

    asa_device.native.send_command_timing.side_effect = results

    with pytest.raises(asa_module.CommandListError, match=commands[1]):
        asa_device.config_list(commands)


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

    result = asa_device.show_list(commands)
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
        asa_device.show_list(commands)


def test_save(asa_device):
    result = asa_device.save()

    assert result
    asa_device.native.send_command_timing.assert_any_call("copy running-config startup-config")


def test_reboot(asa_device):
    asa_device.reboot()
    asa_device.native.send_command_timing.assert_any_call("reload")


def test_reboot_with_timer(asa_device):
    asa_device.reboot(timer=5)
    asa_device.native.send_command_timing.assert_any_call("reload in 5")


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
    expected = asa_device.show("show running config")
    assert asa_device.running_config == expected


def test_starting_config(asa_device):
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
def test_file_copy_transfer_file_does_not_transfer(
    mock_open,
    mock_file_copy_instance,
    mock_cisco_asa_file_transfer,
    mock_file_copy_remote_exists,
    mock_enable,
    asa_device,
):
    args = ("a.txt", "a.txt", "flash:")
    mock_file_copy_instance.return_value = mock_cisco_asa_file_transfer
    with pytest.raises(asa_module.FileTransferError) as err:
        asa_device._file_copy(*args)
    mock_enable.assert_called()
    mock_file_copy_remote_exists.assert_has_calls([mock.call(*args)] * 2)
    mock_cisco_asa_file_transfer.establish_scp_conn.assert_called_once()
    mock_cisco_asa_file_transfer.transfer_file.assert_called_once()
    mock_cisco_asa_file_transfer.close_scp_chan.assert_called_once()
    assert err.value.message == "Attempted file copy, but could not validate file existed after transfer"


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
def test_enable_scp_device_not_active(mock_save, mock_config, mock_peer_device, mock_is_active, asa_device):
    mock_peer_device.return_value = asa_device
    with pytest.raises(asa_module.FileTransferError) as err:
        asa_device.enable_scp()
    assert err.value.message == "Unable to establish a connection with the active device"
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
def test_enable_scp_enable_fail(mock_save, mock_config, mock_peer_device, mock_is_active, asa_device):
    with pytest.raises(asa_module.FileTransferError) as err:
        asa_device.enable_scp()
    assert err.value.message == "Unable to enable scopy on the device"
    mock_config.assert_called_with("ssh scopy enable")
    mock_save.assert_not_called()


@mock.patch.object(os.path, "basename", return_value="a.txt")
@mock.patch.object(ASADevice, "_get_file_system", return_value="flash:")
@mock.patch.object(ASADevice, "enable_scp")
@mock.patch.object(ASADevice, "_file_copy")
def test_file_copy_no_peer_no_args(mock_file_copy, mock_enable_scp, mock_get_file_system, mock_basename, asa_device):
    asa_device.file_copy("path/to/a.txt")
    mock_basename.assert_called()
    mock_get_file_system.assert_called()
    mock_enable_scp.assert_called()
    mock_file_copy.assert_called_once()
    mock_file_copy.assert_called_with("path/to/a.txt", "a.txt", "flash:")


@mock.patch.object(os.path, "basename")
@mock.patch.object(ASADevice, "_get_file_system")
@mock.patch.object(ASADevice, "enable_scp")
@mock.patch.object(ASADevice, "_file_copy")
def test_file_copy_no_peer_pass_args(mock_file_copy, mock_enable_scp, mock_get_file_system, mock_basename, asa_device):
    args = ("path/to/a.txt", "b.txt", "bootflash:")
    asa_device.file_copy(*args)
    mock_basename.assert_not_called()
    mock_get_file_system.assert_not_called()
    mock_enable_scp.assert_called()
    mock_file_copy.assert_called_once()
    mock_file_copy.assert_called_with(*args)


@mock.patch.object(os.path, "basename")
@mock.patch.object(ASADevice, "_get_file_system")
@mock.patch.object(ASADevice, "enable_scp")
@mock.patch.object(ASADevice, "_file_copy")
@mock.patch.object(ASADevice, "peer_device")
def test_file_copy_include_peer(
    mock_peer_device, mock_file_copy, mock_enable_scp, mock_get_file_system, mock_basename, asa_device
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
    ),
    ids=(ACTIVE, "standby_ready", NEGOTIATION, FAILED, "cold_standby", "unsupported"),
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
