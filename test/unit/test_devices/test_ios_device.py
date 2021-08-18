import unittest
import mock
import os

import pytest

from .device_mocks.ios import send_command, send_command_expect
from pyntc.devices.base_device import RollbackError
from pyntc.devices import IOSDevice
from pyntc.devices import ios_device as ios_module


BOOT_IMAGE = "c3560-advipservicesk9-mz.122-44.SE"
BOOT_OPTIONS_PATH = "pyntc.devices.ios_device.IOSDevice.boot_options"
DEVICE_FACTS = {
    "version": "15.1(3)T4",
    "hostname": "rtr2811",
    "uptime": "2 weeks, 4 days, 18 hours, 59 minutes",
    "running_image": "c2800nm-adventerprisek9_ivs_li-mz.151-3.T4.bin",
    "hardware": "2811",
    "serial": "",
    "config_register": "0x2102",
}
SHOW_BOOT_VARIABLE = (
    "Current Boot Variables:\n"
    "BOOT variable = flash:/cat3k_caa-universalk9.16.11.03a.SPA.bin;\n\n"
    "Boot Variables on next reload:\n"
    f"BOOT variable = flash:/{BOOT_IMAGE};\n"
    "Manual Boot = no\n"
    "Enable Break = no\n"
    "Boot Mode = DEVICE\n"
    "iPXE Timeout = 0"
)

SHOW_BOOT_PATH_LIST = (
    f"BOOT path-list      : {BOOT_IMAGE}\n"
    "Config file         : flash:/config.text\n"
    "Private Config file : flash:/private-config.text\n"
    "Enable Break        : yes\n"
    "Manual Boot         : no\n"
    "Allow Dev Key         : yes\n"
    "HELPER path-list    :  \n"
    "Auto upgrade        : yes\n"
    "Auto upgrade path   :  \n"
    "Boot optimization   : disabled\n"
    "NVRAM/Config file\n"
    "      buffer size:   524288\n"
    "Timeout for Config\n"
    "          Download:    0 seconds\n"
    "Config Download\n"
    "      via DHCP:       disabled (next boot: disabled)"
)


class TestIOSDevice(unittest.TestCase):
    @mock.patch.object(IOSDevice, "open")
    @mock.patch.object(IOSDevice, "close")
    @mock.patch("netmiko.cisco.cisco_ios.CiscoIosSSH", autospec=True)
    def setUp(self, mock_miko, mock_close, mock_open):
        self.device = IOSDevice("host", "user", "pass")

        mock_miko.send_command_timing.side_effect = send_command
        mock_miko.send_command_expect.side_effect = send_command_expect
        self.device.native = mock_miko

    def tearDown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()

    def test_bad_show(self):
        command = "show microsoft"
        self.device.native.send_command.return_value = "Error: Microsoft"
        with self.assertRaises(ios_module.CommandError):
            self.device.show(command)

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        results = ["Error: badcommand", "14:31:57.089 PST Tue Feb 10 2008"]

        self.device.native.send_command.side_effect = results

        with self.assertRaisesRegex(ios_module.CommandListError, "show badcommand"):
            self.device.show_list(commands)

    def test_save(self):
        result = self.device.save()
        self.assertTrue(result)
        self.device.native.send_command_timing.assert_any_call("copy running-config startup-config")

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists(self, mock_ft):
        self.device.native.send_command.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertTrue(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_bad_md5(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = False

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_not(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    @mock.patch.object(IOSDevice, "open")
    def test_file_copy(self, mock_open, mock_ft):
        self.device.native.send_command.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(self.device.native, "path/to/source_file", "source_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()
        mock_open.assert_called_once()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    @mock.patch.object(IOSDevice, "open")
    def test_file_copy_different_dest(self, mock_open, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value

        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("source_file", "dest_file")

        mock_ft.assert_called_with(self.device.native, "source_file", "dest_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()
        mock_open.assert_called_once()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    @mock.patch.object(IOSDevice, "open")
    def test_file_copy_fail(self, mock_open, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = Exception
        mock_ft_instance.check_file_exists.return_value = False

        with self.assertRaises(ios_module.FileTransferError):
            self.device.file_copy("source_file")

        mock_open.assert_not_called()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    @mock.patch.object(IOSDevice, "open")
    def test_file_copy_socket_closed_good_md5(self, mock_open, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = OSError
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        mock_ft_instance.compare_md5.side_effect = [True, True]

        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(self.device.native, "path/to/source_file", "source_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()
        mock_ft_instance.compare_md5.assert_has_calls([mock.call(), mock.call()])
        mock_open.assert_called_once()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    @mock.patch.object(IOSDevice, "open")
    def test_file_copy_fail_socket_closed_bad_md5(self, mock_open, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = OSError
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = False

        with self.assertRaises(ios_module.SocketClosedError):
            self.device.file_copy("source_file")

        mock_ft_instance.compare_md5.assert_called_once()
        mock_open.assert_not_called()

    def test_reboot(self):
        self.device.reboot()
        self.device.native.send_command_timing.assert_any_call("reload")

    def test_reboot_with_timer(self):
        self.device.reboot(timer=5)
        self.device.native.send_command_timing.assert_any_call("reload in 5")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="bootflash:")
    def test_boot_options_show_bootvar(self, mock_boot):
        self.device.native.send_command.side_effect = None
        self.device.native.send_command.return_value = f"BOOT variable = bootflash:{BOOT_IMAGE}"
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command.assert_called_with("show bootvar")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="bootflash:")
    def test_boot_options_show_run(self, mock_boot):
        results = [
            ios_module.CommandError("show bootvar", "fail"),
            ios_module.CommandError("show bootvar", "fail"),
            f"boot system flash bootflash:/{BOOT_IMAGE}",
            "Directory of bootflash:/",
        ]
        self.device.native.send_command.side_effect = results
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command.assert_called_with("show run | inc boot")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    def test_rollback(self, mock_boot):
        self.device.rollback("good_checkpoint")
        self.device.native.send_command.assert_called_with("configure replace flash:good_checkpoint force")

    def test_bad_rollback(self):
        # TODO: change to what the protocol would return
        self.device.native.send_command.return_value = "Error: rollback unsuccessful"
        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpoint(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.send_command_timing.assert_any_call("copy running-config good_checkpoint")

    @mock.patch.object(IOSDevice, "_raw_version_data", autospec=True)
    def test_uptime(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        uptime = self.device.uptime
        assert uptime == 413940

    @mock.patch.object(IOSDevice, "_raw_version_data", autospec=True)
    def test_uptime_string(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        uptime_string = self.device.uptime_string
        assert uptime_string == "04:18:59:00"

    def test_vendor(self):
        vendor = self.device.vendor
        assert vendor == "cisco"

    @mock.patch.object(IOSDevice, "_raw_version_data", autospec=True)
    def test_os_version(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        os_version = self.device.os_version
        assert os_version == "15.1(3)T4"

    @mock.patch.object(IOSDevice, "_interfaces_detailed_list", autospec=True)
    def test_interfaces(self, mock_get_intf_list):
        expected = [{"intf": "FastEthernet0/0"}, {"intf": "FastEthernet0/1"}]
        mock_get_intf_list.return_value = expected
        interfaces = self.device.interfaces
        assert interfaces == ["FastEthernet0/0", "FastEthernet0/1"]

    @mock.patch.object(IOSDevice, "_raw_version_data", autospec=True)
    def test_hostname(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        hostname = self.device.hostname
        assert hostname == "rtr2811"

    def test_fqdn(self):
        fqdn = self.device.fqdn
        assert fqdn == "N/A"

    @mock.patch.object(IOSDevice, "_raw_version_data", autospec=True)
    def test_serial_number(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        serial_number = self.device.serial_number
        assert serial_number == ""

    @mock.patch.object(IOSDevice, "_raw_version_data", autospec=True)
    def test_model(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        model = self.device.model
        assert model == "2811"

    @mock.patch.object(IOSDevice, "_raw_version_data", autospec=True)
    def test_config_register(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        config_register = self.device.config_register
        assert config_register == "0x2102"

    def test_running_config(self):
        expected = self.device.show("show running-config")
        self.assertEqual(self.device.running_config, expected)

    def test_starting_config(self):
        expected = self.device.show("show startup-config")
        self.assertEqual(self.device.startup_config, expected)

    def test_enable_from_disable(self):
        self.device.native.check_enable_mode.return_value = False
        self.device.native.check_config_mode.return_value = False
        self.device.enable()
        self.device.native.check_enable_mode.assert_called()
        self.device.native.enable.assert_called()
        self.device.native.check_config_mode.assert_called()
        self.device.native.exit_config_mode.assert_not_called()

    def test_enable_from_enable(self):
        self.device.native.check_enable_mode.return_value = True
        self.device.native.check_config_mode.return_value = False
        self.device.enable()
        self.device.native.check_enable_mode.assert_called()
        self.device.native.enable.assert_not_called()
        self.device.native.check_config_mode.assert_called()
        self.device.native.exit_config_mode.assert_not_called()

    def test_enable_from_config(self):
        self.device.native.check_enable_mode.return_value = True
        self.device.native.check_config_mode.return_value = True
        self.device.enable()
        self.device.native.check_enable_mode.assert_called()
        self.device.native.enable.assert_not_called()
        self.device.native.check_config_mode.assert_called()
        self.device.native.exit_config_mode.assert_called()

    @mock.patch.object(IOSDevice, "_image_booted", side_effect=[False, True])
    @mock.patch.object(IOSDevice, "set_boot_options")
    @mock.patch.object(IOSDevice, "reboot")
    @mock.patch.object(IOSDevice, "_wait_for_device_reboot")
    @mock.patch.object(IOSDevice, "fast_cli", new_callable=mock.PropertyMock)
    def test_install_os(self, mock_fast_cli, mock_wait, mock_reboot, mock_set_boot, mock_image_booted):
        state = self.device.install_os(BOOT_IMAGE)
        mock_set_boot.assert_called()
        mock_reboot.assert_called()
        mock_wait.assert_called()
        mock_fast_cli.fast_cli.assert_not_called()
        self.assertEqual(state, True)

    @mock.patch.object(IOSDevice, "_image_booted", side_effect=[True])
    @mock.patch.object(IOSDevice, "set_boot_options")
    @mock.patch.object(IOSDevice, "reboot")
    @mock.patch.object(IOSDevice, "_wait_for_device_reboot")
    def test_install_os_already_installed(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted):
        state = self.device.install_os(BOOT_IMAGE)
        mock_image_booted.assert_called_once()
        mock_set_boot.assert_not_called()
        mock_reboot.assert_not_called()
        mock_wait.assert_not_called()
        self.assertEqual(state, False)

    @mock.patch.object(IOSDevice, "_image_booted", side_effect=[False, False])
    @mock.patch.object(IOSDevice, "set_boot_options")
    @mock.patch.object(IOSDevice, "reboot")
    @mock.patch.object(IOSDevice, "_wait_for_device_reboot")
    @mock.patch.object(IOSDevice, "_raw_version_data")
    def test_install_os_error(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        self.assertRaises(ios_module.OSInstallError, self.device.install_os, BOOT_IMAGE)


if __name__ == "__main__":
    unittest.main()


def test_check_command_output_for_errors(ios_device):
    command_passes = ios_device._check_command_output_for_errors("valid command", "valid output")
    assert command_passes is None


@pytest.mark.parametrize("output", (r"% invalid output", "Error: invalid output"))
def test_check_command_output_for_errors_error(output, ios_device):
    with pytest.raises(ios_module.CommandError) as err:
        ios_device._check_command_output_for_errors("invalid command", output)
    assert err.value.command == "invalid command"
    assert err.value.cli_error_msg == output


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_pass_string(mock_enter_config, mock_check_for_errors, ios_config):
    command = "no service pad"
    device = ios_config(["no_service_pad.txt"])
    result = device.config(command)

    assert isinstance(result, str)  # TODO: Change to list when deprecating config_list
    mock_enter_config.assert_called_once()
    mock_check_for_errors.assert_called_with(command, result)
    mock_check_for_errors.assert_called_once()
    device.native.send_config_set.assert_called_with(command, enter_config_mode=False, exit_config_mode=False)
    device.native.send_config_set.assert_called_once()
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_pass_list(mock_enter_config, mock_check_for_errors, ios_config):
    command = ["interface Gig0", "description x-connect"]
    device = ios_config([f"{cmd}.txt" for cmd in command])
    result = device.config(command)

    assert isinstance(result, list)
    assert len(result) == 2
    mock_enter_config.assert_called_once()
    mock_check_for_errors.assert_has_calls(mock.call(command[index], result[index]) for index in range(2))
    device.native.send_config_set.assert_has_calls(
        mock.call(cmd, enter_config_mode=False, exit_config_mode=False) for cmd in command
    )
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_pass_netmiko_args(mock_enter_config, mock_check_for_errors, ios_config):
    command = ["a"]
    device = ios_config([1])
    netmiko_args = {"strip_prompt": True}
    device.config(command, **netmiko_args)

    device.native.send_config_set.assert_called_with(
        command[0], enter_config_mode=False, exit_config_mode=False, strip_prompt=True
    )


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_pass_invalid_netmiko_args(mock_enter_config, mock_check_for_errors, ios_config):
    error_message = "send_config_set() got an unexpected keyword argument 'invalid_arg'"
    device = ios_config([TypeError(error_message)])
    netmiko_args = {"invalid_arg": True}
    with pytest.raises(TypeError) as error:
        device.config("command", **netmiko_args)

    assert error.value.args[0] == (f"Netmiko Driver's {error_message}")
    mock_check_for_errors.assert_not_called()
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_disable_enter_config(mock_enter_config, mock_check_for_errors, ios_config):
    command = ["a"]
    config_effects = [1]
    device = ios_config(config_effects)
    device.config(command, enter_config_mode=False)

    device.native.send_config_set.assert_called_with(command[0], enter_config_mode=False, exit_config_mode=False)
    mock_enter_config.assert_not_called()
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_disable_exit_config(mock_enter_config, mock_check_for_errors, ios_config):
    command = ["a"]
    config_effects = [1]
    device = ios_config(config_effects)
    device.config(command, exit_config_mode=False)

    device.native.send_config_set.assert_called_with(command[0], enter_config_mode=False, exit_config_mode=False)
    mock_enter_config.assert_called_once()
    device.native.exit_config_mode.assert_not_called()


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_pass_invalid_string_command(mock_enter_config, mock_check_for_errors, ios_config):
    command = "invalid command"
    result = r"% invalid output"
    mock_check_for_errors.side_effect = [ios_module.CommandError(command, result)]
    device = ios_config(result)
    with pytest.raises(ios_module.CommandError) as err:
        device.config(command)

    device.native.send_config_set.assert_called_with(command, enter_config_mode=False, exit_config_mode=False)
    mock_check_for_errors.assert_called_once()
    device.native.exit_config_mode.assert_called_once()
    assert err.value.command == command
    assert err.value.cli_error_msg == result


@mock.patch.object(IOSDevice, "_check_command_output_for_errors")
@mock.patch.object(IOSDevice, "_enter_config")
def test_config_pass_invalid_list_command(mock_enter_config, mock_check_for_errors, ios_config):
    mock_check_for_errors.side_effect = [
        "valid output",
        ios_module.CommandError("invalid command", r"% invalid output"),
    ]
    command = ["valid command", "invalid command", "another valid command"]
    result = ["valid output", r"% invalid output"]
    device = ios_config(result)
    with pytest.raises(ios_module.CommandListError) as err:
        device.config(command)

    device.native.send_config_set.assert_has_calls(
        (
            mock.call(command[0], enter_config_mode=False, exit_config_mode=False),
            mock.call(command[1], enter_config_mode=False, exit_config_mode=False),
        )
    )
    assert (
        mock.call(command[2], enter_config_mode=False, exit_config_mode=False)
        not in device.native.send_config_set.call_args_list
    )
    mock_check_for_errors.assert_called_with(command[1], result[1])
    device.native.exit_config_mode.assert_called_once()
    assert err.value.commands == command[:2]
    assert err.value.command == command[1]


@mock.patch.object(IOSDevice, "config")
def test_config_list(mock_config, ios_device):
    config_commands = ["a", "b"]
    ios_device.config_list(config_commands)
    mock_config.assert_called_with(config_commands)


@mock.patch.object(IOSDevice, "config")
def test_config_list_pass_netmiko_args(mock_config, ios_device):
    config_commands = ["a", "b"]
    ios_device.config_list(config_commands, strip_prompt=True)
    mock_config.assert_called_with(config_commands, strip_prompt=True)


@mock.patch.object(IOSDevice, "running_config", new_callable=mock.PropertyMock)
def test_backup_running_config(mock_running_config, ios_device):
    mock_running_config_return_value = "This\nis\na\nmock\nconfig\n"
    mock_running_config.return_value = mock_running_config_return_value
    filename = "local_running_config"
    ios_device.backup_running_config(filename)
    with open(filename, "r") as f:
        contents = f.read()
    os.remove(filename)
    assert contents == mock_running_config_return_value
    mock_running_config.assert_called()


@mock.patch.object(IOSDevice, "is_active")
@mock.patch.object(IOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
def test_confirm_is_active(mock_redundancy_state, mock_is_active, ios_device):
    mock_is_active.return_value = True
    actual = ios_device.confirm_is_active()
    assert actual is True
    mock_redundancy_state.assert_not_called()


@mock.patch.object(IOSDevice, "is_active")
@mock.patch.object(IOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "close")
@mock.patch.object(IOSDevice, "open")
@mock.patch("pyntc.devices.ios_device.ConnectHandler")
def test_confirm_is_active_not_active(
    mock_connect_handler, mock_open, mock_close, mock_redundancy_state, mock_peer_redundancy_state, mock_is_active
):
    mock_is_active.return_value = False
    mock_redundancy_state.return_value = "standby hot"
    device = IOSDevice("host", "user", "password")
    with pytest.raises(ios_module.DeviceNotActiveError):
        device.confirm_is_active()

    mock_redundancy_state.assert_called_once()
    mock_peer_redundancy_state.assert_called_once()
    mock_close.assert_called_once()


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_connected_getter(expected, ios_device):
    ios_device._connected = expected
    assert ios_device.connected is expected


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_connected_setter(expected, ios_device):
    ios_device._connected = not expected
    assert ios_device._connected is not expected
    ios_device.connected = expected
    assert ios_device._connected is expected


@mock.patch.object(IOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
@pytest.mark.parametrize(
    "redundancy_state,expected",
    (
        ("active", True),
        ("standby hot", False),
        (None, True),
    ),
    ids=("active", "standby_hot", "unsupported"),
)
def test_is_active(mock_redundancy_state, ios_device, redundancy_state, expected):
    mock_redundancy_state.return_value = redundancy_state
    actual = ios_device.is_active()
    assert actual is expected


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_prompt_found(mock_connected, mock_connect_handler, ios_device):
    mock_connected.return_value = True
    ios_device.open()
    assert ios_device._connected is True
    ios_device.native.find_prompt.assert_called()
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_not_called()


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_prompt_not_found(mock_connected, mock_connect_handler, ios_device):
    mock_connected.side_effect = [True, False]
    ios_device.native.find_prompt.side_effect = [Exception]
    ios_device.open()
    assert ios_device._connected is True
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_called()


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_not_connected(mock_connected, mock_connect_handler, ios_device):
    mock_connected.return_value = False
    ios_device._connected = False
    ios_device.open()
    assert ios_device._connected is True
    ios_device.native.find_prompt.assert_not_called()
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_called()


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "confirm_is_active")
def test_open_standby(mock_confirm, mock_connected, mock_connect_handler, ios_device):
    mock_connected.side_effect = [False, False, True]
    mock_confirm.side_effect = [ios_module.DeviceNotActiveError("host1", "standby", "active")]
    with pytest.raises(ios_module.DeviceNotActiveError):
        ios_device.open()

    ios_device.native.find_prompt.assert_not_called()
    mock_connected.assert_has_calls((mock.call(),) * 2)


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy", "standby hot"),
        ("show_redundancy_no_peer", "disabled"),
    ),
    ids=("standby_hot", "disabled"),
)
def test_peer_redundancy_state(filename, expected, ios_show):
    device = ios_show([f"{filename}.txt"])
    actual = device.peer_redundancy_state
    assert actual == expected


def test_peer_redundancy_state_unsupported(ios_show):
    device = ios_show([ios_module.CommandError("show redundancy", "unsupported")])
    actual = device.peer_redundancy_state
    assert actual is None


def test_re_show_redundancy(ios_show, ios_redundancy_info, ios_redundancy_self, ios_redundancy_other):
    device = ios_show(["show_redundancy.txt"])
    show_redundancy = device.show("show redundancy")
    re_show_redundancy = ios_module.RE_SHOW_REDUNDANCY.match(show_redundancy)
    assert re_show_redundancy.groupdict() == {
        "info": ios_redundancy_info,
        "self": ios_redundancy_self,
        "other": ios_redundancy_other,
    }


def test_re_show_redundancy_no_peer(ios_show, ios_redundancy_info, ios_redundancy_self):
    device = ios_show(["show_redundancy_no_peer.txt"])
    show_redundancy = device.show("show redundancy")
    re_show_redundancy = ios_module.RE_SHOW_REDUNDANCY.match(show_redundancy)
    assert re_show_redundancy.groupdict() == {
        "info": ios_redundancy_info,
        "self": ios_redundancy_self,
        "other": None,
    }


def test_re_redundancy_operation_mode(ios_redundancy_info):
    re_operational_mode = ios_module.RE_REDUNDANCY_OPERATION_MODE.search(ios_redundancy_info)
    assert re_operational_mode.group(1) == "Stateful Switchover"


@pytest.mark.parametrize(
    "output,expected",
    (
        ("a\n  Current Software state = ACTIVE \n  b", "ACTIVE"),
        ("a\n  Current Software state = STANDBY HOT \n  b", "STANDBY HOT"),
    ),
    ids=("active", "standby_hot"),
)
def test_re_redundancy_state(output, expected):
    re_redundancy_state = ios_module.RE_REDUNDANCY_STATE.search(output)
    actual = re_redundancy_state.group(1)
    assert actual == expected


def test_redundancy_mode(ios_show):
    device = ios_show(["show_redundancy.txt"])
    actual = device.redundancy_mode
    assert actual == "stateful switchover"


def test_redundancy_mode_unsupported_command(ios_show):
    device = ios_show([ios_module.CommandError("show redundancy", "unsupported")])
    actual = device.redundancy_mode
    assert actual == "n/a"


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy", "active"),
        ("show_redundancy_standby", "standby hot"),
    ),
    ids=("active", "standby_hot"),
)
def test_redundancy_state(filename, expected, ios_show):
    device = ios_show([f"{filename}.txt"])
    actual = device.redundancy_state
    assert actual == expected


def test_redundancy_state_unsupported(ios_show):
    device = ios_show([ios_module.CommandError("show redundancy", "unsupported")])
    actual = device.redundancy_state
    assert actual is None


def test_get_file_system(ios_show):
    filename = "dir"
    expected = "flash:"
    device = ios_show([f"{filename}.txt"])
    actual = device._get_file_system()
    assert actual == expected


def test_get_file_system_first_error_then_pass(ios_show):
    filename = "dir"
    expected = "flash:"
    device = ios_show(["", f"{filename}.txt"])
    actual = device._get_file_system()
    assert actual == expected

    device.show.assert_has_calls([mock.call("dir")] * 2)


@mock.patch.object(IOSDevice, "hostname", new_callable=mock.PropertyMock)
def test_get_file_system_raise_error(mock_hostname, ios_show):
    # Set the command to run 5 times
    device = ios_show([""] * 5)

    # Set a return value for the Facts mock
    mock_hostname.return_value = "pyntc-rtr"

    # Test with the raises
    with pytest.raises(ios_module.FileSystemNotFoundError):
        device._get_file_system()

    # Assert of the calls
    device.show.assert_has_calls([mock.call("dir")] * 5)


def test_send_command_error(ios_send_command):
    command = "send_command_error"
    device = ios_send_command([f"{command}.txt"])
    with pytest.raises(ios_module.CommandError):
        device._send_command(command)
    device.native.send_command.assert_called()


def test_send_command_expect(ios_send_command):
    command = "send_command_expect"
    device = ios_send_command([f"{command}.txt"])
    device._send_command(command, expect_string="Continue?")
    device.native.send_command.assert_called_with(command_string="send_command_expect", expect_string="Continue?")


def test_send_command_timing(ios_send_command_timing):
    command = "send_command_timing"
    device = ios_send_command_timing([f"{command}.txt"])
    device.native.send_command_timing(command)
    device.native.send_command_timing.assert_called()
    device.native.send_command_timing.assert_called_with(command)


@mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
@mock.patch.object(IOSDevice, "config")
@mock.patch.object(IOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "save")
def test_set_boot_options(mock_save, mock_boot_options, mock_config, mock_file_system, ios_show):
    device = ios_show(["dir_flash:.txt"])
    mock_boot_options.return_value = {"sys": BOOT_IMAGE}
    device.set_boot_options(BOOT_IMAGE)
    mock_config.assert_called_with(["no boot system", f"boot system flash:/{BOOT_IMAGE}"])
    mock_file_system.assert_called_once()
    mock_config.assert_called_once()
    mock_save.assert_called_once()
    mock_boot_options.assert_called_once()


@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "config")
@mock.patch.object(IOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "save")
def test_set_boot_options_pass_file_system(mock_save, mock_boot_options, mock_config, mock_file_system, ios_show):
    device = ios_show(["dir_flash:.txt"])
    mock_boot_options.return_value = {"sys": BOOT_IMAGE}
    device.set_boot_options(BOOT_IMAGE, file_system="flash:")
    mock_config.assert_called_with(["no boot system", f"boot system flash:/{BOOT_IMAGE}"])
    mock_file_system.assert_not_called()
    mock_config.assert_called_once()
    mock_save.assert_called_once()
    mock_boot_options.assert_called_once()


@mock.patch.object(IOSDevice, "config")
@mock.patch.object(IOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "save")
def test_set_boot_options_with_spaces(mock_save, mock_boot_options, mock_config, ios_show):
    device = ios_show(["dir_flash:.txt"])
    mock_config.side_effect = [
        ios_module.CommandListError(
            ["no boot system", "invalid boot command"],
            "invalid boot command",
            r"% Invalid command",
        ),
        "valid boot command",
    ]
    mock_boot_options.return_value = {"sys": BOOT_IMAGE}
    device.set_boot_options(BOOT_IMAGE, file_system="flash:")
    mock_config.assert_has_calls(
        [
            mock.call(["no boot system", f"boot system flash:/{BOOT_IMAGE}"]),
            mock.call(["no boot system", f"boot system flash {BOOT_IMAGE}"]),
        ]
    )
    mock_save.assert_called_once()


@mock.patch.object(IOSDevice, "hostname", new_callable=mock.PropertyMock)
def test_set_boot_options_no_file(mock_hostname, ios_show):
    bad_image = "bad_image.bin"
    host = "ios_host"
    file_system = "flash:"
    mock_hostname.return_value = host
    device = ios_show(["dir_flash:.txt"])
    with pytest.raises(ios_module.NTCFileNotFoundError) as err:
        device.set_boot_options(bad_image, file_system=file_system)

    assert err.value.message == f"{bad_image} was not found in {file_system} on {host}"


@mock.patch.object(IOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "config")
@mock.patch.object(IOSDevice, "save")
def test_set_boot_options_bad_boot(mock_save, mock_config, mock_boot_options, ios_show):
    bad_image = "bad_image.bin"
    mock_boot_options.return_value = {"sys": bad_image}
    device = ios_show(["dir_flash:.txt"])
    with pytest.raises(ios_module.CommandError) as err:
        device.set_boot_options(BOOT_IMAGE, file_system="flash:")

    assert err.value.command == f"boot system flash:/{BOOT_IMAGE}"
    assert err.value.cli_error_msg == f"Setting boot command did not yield expected results, found {bad_image}"


#
# TESTS FOR IOS INSTALL MODE METHOD
#

# Test install mode upgrade for install mode with latest method
@mock.patch.object(IOSDevice, "os_version", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_image_booted")
@mock.patch.object(IOSDevice, "set_boot_options")
@mock.patch.object(IOSDevice, "show")
@mock.patch.object(IOSDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "reboot")
@mock.patch.object(IOSDevice, "fast_cli", new_callable=mock.PropertyMock)
def test_install_os_install_mode(
    mock_fast_cli,
    mock_reboot,
    mock_get_file_system,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    mock_os_version,
    ios_device,
):
    image_name = "cat9k_iosxe.16.12.04.SPA.bin"
    file_system = "flash:"
    mock_get_file_system.return_value = file_system
    mock_os_version.return_value = "16.12.03a"
    mock_image_booted.side_effect = [False, True]
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install os function
    actual = ios_device.install_os(image_name, install_mode=True)

    # Check the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"install add file {file_system}{image_name} activate commit prompt-level none", delay_factor=20
    )
    mock_reboot.assert_not_called()
    mock_os_version.assert_called()
    mock_image_booted.assert_called()
    mock_wait_for_reboot.assert_called()
    assert actual is True
    # Assert that fast_cli value was retrieved, set to Fals, and set back to original value
    assert mock_fast_cli.call_count == 3


# Test install mode upgrade fail
@mock.patch.object(IOSDevice, "os_version", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_image_booted")
@mock.patch.object(IOSDevice, "set_boot_options")
@mock.patch.object(IOSDevice, "show")
@mock.patch.object(IOSDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "reboot")
@mock.patch.object(IOSDevice, "hostname", new_callable=mock.PropertyMock)
def test_install_os_install_mode_failed(
    mock_hostname,
    mock_reboot,
    mock_get_file_system,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    mock_os_version,
    ios_device,
):
    mock_hostname.return_value = "ntc-rtr01"
    image_name = "cat9k_iosxe.16.12.04.SPA.bin"
    file_system = "flash:"
    mock_get_file_system.return_value = file_system
    mock_os_version.return_value = "16.12.03a"
    mock_image_booted.side_effect = [False, False]
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install os function
    with pytest.raises(ios_module.OSInstallError) as err:
        ios_device.install_os(image_name, install_mode=True)

    assert err.value.message == "ntc-rtr01 was unable to boot into cat9k_iosxe.16.12.04.SPA.bin"

    # Check the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"install add file {file_system}{image_name} activate commit prompt-level none", delay_factor=20
    )
    mock_reboot.assert_not_called()
    mock_os_version.assert_called()
    mock_image_booted.assert_called()
    mock_wait_for_reboot.assert_called()


# Test install mode upgrade for install mode with latest method
@mock.patch.object(IOSDevice, "os_version", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_image_booted")
@mock.patch.object(IOSDevice, "set_boot_options")
@mock.patch.object(IOSDevice, "show")
@mock.patch.object(IOSDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "reboot")
def test_install_os_install_mode_no_upgrade(
    mock_reboot,
    mock_get_file_system,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    mock_os_version,
    ios_device,
):
    image_name = "cat9k_iosxe.16.12.04.SPA.bin"
    file_system = "flash:"
    mock_get_file_system.return_value = file_system
    mock_os_version.return_value = "16.12.03a"
    mock_image_booted.side_effect = [True, True]
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install os function
    actual = ios_device.install_os(image_name, install_mode=True)

    # Check the results
    mock_set_boot_options.assert_not_called()
    mock_show.assert_not_called()
    mock_reboot.assert_not_called()
    mock_os_version.assert_not_called()
    mock_image_booted.assert_called_once()
    mock_wait_for_reboot.assert_not_called()
    assert actual is False


#
# FROM CISCO IOS EVEREST VERSION TESTS
#

# Test install mode upgrade for install mode with interim method on OS Version
@mock.patch.object(IOSDevice, "os_version", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_image_booted")
@mock.patch.object(IOSDevice, "set_boot_options")
@mock.patch.object(IOSDevice, "show")
@mock.patch.object(IOSDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "reboot")
def test_install_os_install_mode_from_everest(
    mock_reboot,
    mock_get_file_system,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    mock_os_version,
    ios_device,
):
    image_name = "cat9k_iosxe.16.12.04.SPA.bin"
    file_system = "flash:"
    mock_get_file_system.return_value = file_system
    mock_os_version.return_value = "16.6.1"
    mock_image_booted.side_effect = [False, True]
    # Call the install_os
    actual = ios_device.install_os(image_name, install_mode=True)

    # Test the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"request platform software package install switch all file {file_system}{image_name} auto-copy",
        delay_factor=20,
    )
    mock_reboot.assert_called()
    mock_os_version.assert_called()
    mock_image_booted.assert_called()
    mock_wait_for_reboot.assert_called()
    assert actual is True


# Test install mode upgrade for install mode with interim method on OS Version with error unable to complete
@mock.patch.object(IOSDevice, "os_version", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_image_booted")
@mock.patch.object(IOSDevice, "set_boot_options")
@mock.patch.object(IOSDevice, "show")
@mock.patch.object(IOSDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "reboot")
# Mock hostname for error handling
@mock.patch.object(IOSDevice, "hostname", new_callable=mock.PropertyMock)
def test_install_os_install_mode_from_everest_failed(
    mock_hostname,
    mock_reboot,
    mock_get_file_system,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    mock_os_version,
    ios_device,
):
    mock_hostname.return_value = "ntc-rtr01"
    image_name = "cat9k_iosxe.16.12.04.SPA.bin"
    file_system = "flash:"
    mock_get_file_system.return_value = file_system
    mock_os_version.return_value = "16.6.1"
    mock_image_booted.side_effect = [False, False]
    # Call the install_os
    with pytest.raises(ios_module.OSInstallError) as err:
        ios_device.install_os(image_name, install_mode=True)

    assert err.value.message == "ntc-rtr01 was unable to boot into cat9k_iosxe.16.12.04.SPA.bin"

    # Test the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"request platform software package install switch all file {file_system}{image_name} auto-copy",
        delay_factor=20,
    )
    mock_reboot.assert_called()
    mock_os_version.assert_called()
    mock_image_booted.assert_called()
    mock_wait_for_reboot.assert_called()


# Test install mode upgrade for install mode with interim method on OS Version with error unable to complete
@mock.patch.object(IOSDevice, "os_version", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_image_booted")
@mock.patch.object(IOSDevice, "set_boot_options")
@mock.patch.object(IOSDevice, "show")
@mock.patch.object(IOSDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "reboot")
# Mock hostname for error handling
@mock.patch.object(IOSDevice, "hostname", new_callable=mock.PropertyMock)
def test_install_os_install_mode_from_everest_to_everest(
    mock_hostname,
    mock_reboot,
    mock_get_file_system,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    mock_os_version,
    ios_device,
):
    mock_hostname.return_value = "ntc-rtr01"
    image_name = "cat9k_iosxe.16.05.01a.SPA.bin"
    file_system = "flash:"
    mock_get_file_system.return_value = file_system
    mock_os_version.return_value = "16.5.1"
    mock_image_booted.side_effect = [True, True]
    # Call the install_os
    actual = ios_device.install_os(image_name, install_mode=True)

    # Test the results
    mock_set_boot_options.assert_not_called()
    mock_show.assert_not_called()
    mock_reboot.assert_not_called()
    mock_os_version.assert_not_called()
    mock_image_booted.assert_called_once()
    mock_wait_for_reboot.assert_not_called()
    assert actual is False


@mock.patch.object(IOSDevice, "os_version", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_image_booted")
@mock.patch.object(IOSDevice, "set_boot_options")
@mock.patch.object(IOSDevice, "show")
@mock.patch.object(IOSDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSDevice, "_get_file_system")
@mock.patch.object(IOSDevice, "reboot")
@pytest.mark.parametrize("fast_cli_setting", [True, False], ids=["true", "false"])
def test_install_os_install_mode_fast_cli_state(
    mock_reboot,
    mock_get_file_system,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    mock_os_version,
    ios_device,
    fast_cli_setting,
):
    image_name = "cat9k_iosxe.16.12.04.SPA.bin"
    file_system = "flash:"
    mock_get_file_system.return_value = file_system
    mock_os_version.return_value = "16.12.03a"
    mock_image_booted.side_effect = [False, True]
    ios_device.fast_cli = fast_cli_setting
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install os function
    actual = ios_device.install_os(image_name, install_mode=True)

    # Check the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"install add file {file_system}{image_name} activate commit prompt-level none", delay_factor=20
    )
    mock_reboot.assert_not_called()
    mock_os_version.assert_called()
    mock_image_booted.assert_called()
    mock_wait_for_reboot.assert_called()
    assert actual is True
    assert ios_device.fast_cli == fast_cli_setting


def test_show(ios_send_command):
    command = "show_ip_arp"
    device = ios_send_command([f"{command}.txt"])
    device.show(command)
    device.native.send_command.assert_called_with(command_string="show_ip_arp")
    device.native.send_command.assert_called_once()


def test_show_list(ios_send_command):
    commands = ["show_version", "show_ip_arp"]
    device = ios_send_command([f"{commands[0]}.txt", f"{commands[1]}"])
    device.show_list(commands)
    device.native.send_command.assert_has_calls(
        [mock.call(command_string="show_version"), mock.call(command_string="show_ip_arp")]
    )


@mock.patch.object(IOSDevice, "model", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "_show_vlan")
def test_vlans(mock_show_vlan, mock_model, ios_show):
    mock_model.return_value = "WS-3750"
    device = ios_show(["show_vlan.txt"])
    print(device)
    mock_show_vlan.return_value = [{"vlan_id": "1"}, {"vlan_id": "2"}, {"vlan_id": "3"}, {"vlan_id": "4"}]
    assert device.vlans == ["1", "2", "3", "4"]


@pytest.mark.parametrize("show_boot_out", (SHOW_BOOT_VARIABLE, SHOW_BOOT_PATH_LIST), ids=("bootvar", "bootpath"))
@mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
def test_boot_options_show_boot(mock_boot, show_boot_out, ios_send_command):
    results = [ios_module.CommandError("show bootvar", "fail"), show_boot_out]
    device = ios_send_command(results)
    boot_options = device.boot_options
    assert boot_options == {"sys": BOOT_IMAGE}
    device.native.send_command.assert_called_with(command_string="show boot")


def test_connected_with_fast_cli():
    with mock.patch.object(IOSDevice, "confirm_is_active") as mock_confirm:
        mock_confirm.return_value = True
        with mock.patch("pyntc.devices.ios_device.ConnectHandler") as ch:
            device = IOSDevice("host", "user", "password")
            device.native = ch
    assert device.fast_cli


def test_connected_with_fast_cli_false():
    with mock.patch.object(IOSDevice, "confirm_is_active") as mock_confirm:
        mock_confirm.return_value = True
        with mock.patch("pyntc.devices.ios_device.ConnectHandler") as ch:
            device = IOSDevice("host", "user", "password", fast_cli=False)
            device.native = ch
    assert not device.fast_cli


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_fast_cli(expected, ios_device):
    ios_device._fast_cli = expected
    assert ios_device.fast_cli is expected


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_fast_cli_setter(expected, ios_device):
    ios_device._fast_cli = not expected
    assert ios_device._fast_cli is not expected
    assert ios_device.native.fast_cli is not expected
    ios_device.fast_cli = expected
    assert ios_device._fast_cli is expected
    assert ios_device.native.fast_cli is expected


def test_image_booted_bundle_version(ios_show):
    device = ios_show(["show_version.txt"])
    assert device._image_booted(image_name="c3750-ipservicesk9-mz.150-2.SE11.bin")


def test_image_booted_bundle_version_false(ios_show):
    device = ios_show(["show_version.txt"])
    assert not device._image_booted(image_name="c3750-ipservicesk9-mz.150-2.SE12.bin")


def test_image_booted_install_mode(ios_show):
    device = ios_show(["show_version_install_mode.txt"])
    assert device._image_booted(image_name="c3750-ipservicesk9-mz.16.09.03.SPA.bin")


def test_image_booted_install_mode_fail(ios_show):
    device = ios_show(["show_version_install_mode.txt"])
    assert not device._image_booted(image_name="c3750-ipservicesk9-mz.16.09.04.SPA.bin")
