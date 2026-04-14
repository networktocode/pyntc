import os
import time
import unittest

import mock
import pytest

from pyntc.devices import EOSDevice
from pyntc.devices.base_device import RollbackError
from pyntc.devices.eos_device import FileTransferError
from pyntc.devices.system_features.vlans.eos_vlans import EOSVlans
from pyntc.errors import CommandError, CommandListError
from pyntc.utils.models import FileCopyModel

from .device_mocks.eos import config, enable, send_command, send_command_expect


class TestEOSDevice(unittest.TestCase):
    @mock.patch("pyeapi.client.Node", autospec=True)
    def setUp(self, mock_node):
        self.device = EOSDevice("host", "user", "pass")
        self.maxDiff = None

        mock_node.enable.side_effect = enable
        mock_node.config.side_effect = config
        self.device.native = mock_node

    def tearDown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()

    def test_config_pass_string(self):
        command = "interface Eth1"
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with(command)

    def test_config_pass_list(self):
        commands = ["interface Eth1", "no shutdown"]
        result = self.device.config(commands)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with(commands)

    @mock.patch.object(EOSDevice, "config")
    def test_config_list(self, mock_config):
        commands = ["interface Eth1", "no shutdown"]
        self.device.config(commands)
        self.device.config.assert_called_with(commands)

    def test_bad_config_pass_string(self):
        command = "asdf poknw"
        response = "Error [1002]: asdf_poknw failed [None]"

        with pytest.raises(CommandError) as err:
            self.device.config(command)
        assert err.value.command == command
        assert err.value.cli_error_msg == response

    def test_bad_config_pass_list(self):
        commands = ["interface Eth1", "apons"]
        response = [
            "Valid",
            "\nCommand apons failed with message: Error [1002]: apons failed [None]\nCommand List: \n\tinterface Eth1\n\tapons\n",
        ]

        with pytest.raises(CommandListError) as err:
            self.device.config(commands)
        assert err.value.command == commands[1]
        assert err.value.message == response[1]

    @mock.patch.object(EOSDevice, "_parse_response")
    def test_show_pass_string(self, mock_parse):
        command = "show ip arp"
        return_value = [
            {
                "command": "show ip arp",
                "result": {
                    "ipV4Neighbors": [
                        {"hwAddress": "2cc2.60ff.0011", "interface": "Management1", "age": 0, "address": "10.0.0.2"}
                    ],
                    "notLearnedEntries": 0,
                    "totalEntries": 1,
                    "dynamicEntries": 1,
                    "staticEntries": 0,
                },
                "encoding": "json",
            }
        ]
        mock_parse.return_value = return_value
        result = self.device.show(command)
        assert result == return_value[0]
        self.device._parse_response.assert_called_with([result], raw_text=False)
        self.device.native.enable.assert_called_with([command], encoding="json")

    @mock.patch.object(EOSDevice, "_parse_response")
    def test_show_pass_list(self, mock_parse):
        commands = ["show hostname", "show clock"]
        return_value = [
            {
                "command": "show hostname",
                "result": {"hostname": "eos-spine1", "fqdn": "eos-spine1.ntc.com"},
                "encoding": "json",
            },
            {
                "command": "show clock",
                "result": {"output": "Fri Jan 22 23:29:21 2016\nTimezone: UTC\nClock source: local\n"},
                "encoding": "text",
            },
        ]
        mock_parse.return_value = return_value
        result = self.device.show(commands)
        assert result == return_value
        self.device._parse_response.assert_called_with(result, raw_text=False)
        self.device.native.enable.assert_called_with(commands, encoding="json")

    def test_bad_show_pass_string(self):
        command = "show microsoft"
        response = "Error [1002]: show_microsoft failed [None]"
        with pytest.raises(CommandError) as err:
            self.device.show(command)
        assert err.value.command[0] == "show_microsoft"
        assert err.value.cli_error_msg == response

    def test_bad_show_pass_list(self):
        commands = ["show badcommand", "show clock"]
        response = [
            "\nCommand show_badcommand failed with message: Error [1002]: show_badcommand failed [None]\nCommand List: \n\tshow badcommand\n\tshow clock\n",
            "Valid",
        ]
        with pytest.raises(CommandListError) as err:
            self.device.show(commands)
        assert err.value.command == "show_badcommand"
        assert err.value.message == response[0]

    @mock.patch.object(EOSDevice, "_parse_response")
    def test_show_raw_text(self, mock_parse):
        command = "show hostname"
        mock_parse.return_value = [
            {
                "command": "show hostname",
                "result": {"output": "Hostname: spine1\nFQDN:     spine1.ntc.com\n"},
                "encoding": "text",
            }
        ]
        result = self.device.show(command, raw_text=True)
        self.device._parse_response.assert_called_with([result], raw_text=True)
        self.device.native.enable.assert_called_with([command], encoding="text")

    @mock.patch.object(EOSDevice, "show")
    def test_show_list(self, mock_config):
        commands = ["show hostname", "show clock"]
        self.device.show(commands)
        self.device.show.assert_called_with(commands)

    def test_save(self):
        result = self.device.save()
        self.assertTrue(result)
        self.device.native.enable.assert_called_with(["copy running-config startup-config"], encoding="json")

    @mock.patch("pyeapi.client.Node", autospec=True)
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def setup_test_file_copy_remote_exists(self, test_file_copy_remote_exists, mock_ssh, mock_node):
        self.device = EOSDevice("host", "user", "pass")
        self.maxDiff = None

        mock_node.enable.side_effect = enable
        mock_node.config.side_effect = config
        self.device.native = mock_node
        mock_ssh.send_command_timing.side_effect = send_command
        mock_ssh.send_command_expect.side_effect = send_command_expect
        self.device.native_ssh = mock_ssh

    def teardown_test_file_copy_remote_exists(self, test_file_copy_remote_exists):
        self.device.native.reset_mock()
        self.device.native_ssh.reset_mock()

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_remote_exists(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertTrue(result)

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_remote_exists_bad_md5(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = False

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_remote_not_exist(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(
            self.device.native_ssh, "path/to/source_file", "source_file", file_system="/mnt/flash"
        )
        # mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_different_dest(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("source_file", "dest_file")

        mock_ft.assert_called_with(self.device.native_ssh, "source_file", "dest_file", file_system="/mnt/flash")
        # mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_fail(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = Exception
        mock_ft_instance.check_file_exists.return_value = False

        with self.assertRaises(FileTransferError):
            self.device.file_copy("source_file")

    # TODO: unit test for remote_file_copy

    def test_reboot(self):
        self.device.reboot()
        self.device.native.enable.assert_called_with(["reload now"], encoding="json")

    def test_boot_options(self):
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": "EOS.swi"})

    def test_set_boot_options(self):
        results = [
            [{"result": {"output": "flash:"}}],
            [{"result": {"output": "new_image.swi"}}],
            [{"result": {}}],
            [{"result": {"softwareImage": "flash:/new_image.swi"}}],
        ]
        calls = [
            mock.call(["dir"], encoding="text"),
            mock.call(["dir flash:"], encoding="text"),
            mock.call(["install source flash:new_image.swi"], encoding="json"),
            mock.call(["show boot-config"], encoding="json"),
        ]
        self.device.native.enable.side_effect = results
        self.device.set_boot_options("new_image.swi")
        self.device.native.enable.assert_has_calls(calls)

    def test_backup_running_config(self):
        filename = "local_running_config"
        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        self.assertEqual(contents, self.device.running_config)
        os.remove(filename)

    def test_rollback(self):
        self.device.rollback("good_checkpoint")
        self.device.native.enable.assert_called_with(["configure replace good_checkpoint force"], encoding="json")

    def test_bad_rollback(self):
        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpoint(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.enable.assert_called_with(["copy running-config good_checkpoint"], encoding="json")

    def test_uptime(self):
        sh_version_output = self.device.show("show version")
        expected = int(time.time() - sh_version_output["bootupTimestamp"])
        uptime = self.device.uptime
        self.assertIsInstance(uptime, int)
        self.assertEqual(uptime, expected)

    @mock.patch.object(EOSDevice, "_uptime_to_string", autospec=True)
    def test_uptime_string(self, mock_upt_str):
        mock_upt_str.return_value = "02:00:03:38"
        uptime_string = self.device.uptime_string
        self.assertIsInstance(uptime_string, str)
        self.assertEqual(uptime_string, "02:00:03:38")

    def test_vendor(self):
        vendor = self.device.vendor
        self.assertEqual(vendor, "arista")

    def test_os_version(self):
        os_version = self.device.os_version
        self.assertEqual(os_version, "4.14.7M-2384414.4147M")

    def test_interfaces(self):
        interfaces = self.device.interfaces
        expected = [
            "Ethernet1",
            "Ethernet2",
            "Ethernet3",
            "Ethernet4",
            "Ethernet5",
            "Ethernet6",
            "Ethernet7",
            "Ethernet8",
            "Management1",
        ]
        self.assertEqual(interfaces, expected)

    def test_hostname(self):
        hostname = self.device.hostname
        self.assertEqual(hostname, "eos-spine1")

    def test_fqdn(self):
        fqdn = self.device.fqdn
        self.assertEqual(fqdn, "eos-spine1.ntc.com")

    def test_serial_number(self):
        serial_number = self.device.serial_number
        self.assertEqual(serial_number, "")

    def test_model(self):
        model = self.device.model
        self.assertEqual(model, "vEOS")

    @mock.patch.object(EOSVlans, "get_list", autospec=True)
    def test_vlans(self, mock_vlan_list):
        mock_vlan_list.return_value = ["1", "2", "10"]
        expected = ["1", "2", "10"]
        vlans = self.device.vlans

        self.assertEqual(vlans, expected)

    def test_running_config(self):
        expected = self.device.show("show running-config", raw_text=True)
        self.assertEqual(self.device.running_config, expected)

    def test_starting_config(self):
        expected = self.device.show("show startup-config", raw_text=True)
        self.assertEqual(self.device.startup_config, expected)


if __name__ == "__main__":
    unittest.main()


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_no_transport(mock_eos_connect):
    EOSDevice("host", "username", "password")
    mock_eos_connect.assert_called_with(host="host", username="username", password="password", transport="http")


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_https_transport(mock_eos_connect):
    EOSDevice("host", "username", "password", transport="https")
    mock_eos_connect.assert_called_with(host="host", username="username", password="password", transport="https")


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_pass_port(mock_eos_connect):
    EOSDevice("host", "username", "password", port=8080)
    mock_eos_connect.assert_called_with(
        host="host", username="username", password="password", transport="http", port=8080
    )


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_pass_timeout(mock_eos_connect):
    EOSDevice("host", "username", "password", timeout=30)
    mock_eos_connect.assert_called_with(
        host="host", username="username", password="password", transport="http", timeout=30
    )


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_pass_port_and_timeout(mock_eos_connect):
    EOSDevice("host", "username", "password", port=8080, timeout=30)
    mock_eos_connect.assert_called_with(
        host="host", username="username", password="password", transport="http", port=8080, timeout=30
    )


class TestRemoteFileCopy(unittest.TestCase):
    """Tests for remote_file_copy method."""

    @mock.patch("pyeapi.client.Node", autospec=True)
    def setUp(self, mock_node):
        self.device = EOSDevice("host", "user", "pass")
        self.maxDiff = None
        mock_node.enable.side_effect = enable
        mock_node.config.side_effect = config
        self.device.native = mock_node

    def tearDown(self):
        self.device.native.reset_mock()

    def test_remote_file_copy_invalid_src_type(self):
        """Test remote_file_copy raises TypeError for invalid src type."""
        with self.assertRaises(TypeError) as ctx:
            self.device.remote_file_copy("not_a_model")
        self.assertIn("src must be an instance of FileCopyModel", str(ctx.exception))

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_file_system_auto_detection(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy calls _get_file_system when file_system is not provided."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        self.device.remote_file_copy(src)
        mock_get_fs.assert_called()

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_skip_transfer_on_checksum_match(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy completes when file exists with matching checksum."""
        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        self.device.remote_file_copy(src)
        mock_verify.assert_called()

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_http_transfer(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy executes HTTP transfer correctly."""
        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        self.device.remote_file_copy(src)

        mock_open.assert_called_once()
        mock_enable.assert_called_once()
        mock_ssh.send_command.assert_called()
        call_args = mock_ssh.send_command.call_args
        self.assertIn("copy http://", call_args[0][0])

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_verification_failure(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy raises FileTransferError when verification fails."""
        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = False

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        with self.assertRaises(FileTransferError):
            self.device.remote_file_copy(src)

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_with_default_dest(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy defaults dest to src.file_name."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://server.example.com/myfile.bin",
            checksum="abc123",
            file_name="myfile.bin",
        )

        self.device.remote_file_copy(src)

        mock_verify.assert_called()
        call_args = mock_verify.call_args
        self.assertEqual(call_args[0][1], "myfile.bin")

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_with_explicit_dest(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy uses explicit dest parameter."""
        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        self.device.remote_file_copy(src, dest="custom_name.bin")

        call_args = mock_verify.call_args
        self.assertEqual(call_args[0][1], "custom_name.bin")

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_with_explicit_file_system(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy uses explicit file_system parameter."""
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        self.device.remote_file_copy(src, file_system="flash:")

        mock_get_fs.assert_not_called()
        call_args = mock_ssh.send_command.call_args
        self.assertIn("flash:", call_args[0][0])

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_scp_with_credentials(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy constructs SCP command with username only."""
        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command_timing.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="scp://user:pass@server.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        self.device.remote_file_copy(src)

        call_args = mock_ssh.send_command_timing.call_args
        command = call_args[0][0]
        self.assertIn("scp://", command)
        self.assertIn("user@", command)
        self.assertNotIn("pass@", command)

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_timeout_applied(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy applies timeout to send_command."""
        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        for timeout in [300, 600, 900, 1800]:
            with self.subTest(timeout=timeout):
                src = FileCopyModel(
                    download_url="http://example.com/file.bin",
                    checksum="abc123",
                    file_name="file.bin",
                    timeout=timeout,
                )

                self.device.remote_file_copy(src)

                call_args = mock_ssh.send_command.call_args
                self.assertEqual(call_args[1]["read_timeout"], timeout)

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_checksum_mismatch_raises_error(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy raises FileTransferError on checksum mismatch after transfer."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = False

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
        )

        with self.assertRaises(FileTransferError):
            self.device.remote_file_copy(src)

        mock_ssh.send_command.assert_called()
        call_args = mock_ssh.send_command.call_args
        self.assertIn("copy", call_args[0][0].lower())

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_post_transfer_verification(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy calls verify_file with correct algorithm after transfer."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        for checksum, algorithm in [("abc123def456", "md5"), ("abc123def456789", "sha256")]:
            with self.subTest(algorithm=algorithm):
                src = FileCopyModel(
                    download_url="http://server.example.com/file.bin",
                    checksum=checksum,
                    file_name="file.bin",
                    hashing_algorithm=algorithm,
                )

                self.device.remote_file_copy(src)
                mock_verify.assert_called()

    def test_remote_file_copy_unsupported_scheme(self):
        """Test remote_file_copy raises ValueError for unsupported scheme."""
        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )
        # Override scheme to something unsupported
        src.scheme = "gopher"

        with self.assertRaises(ValueError) as ctx:
            self.device.remote_file_copy(src)
        self.assertIn("Unsupported scheme", str(ctx.exception))

    def test_remote_file_copy_query_string_rejected(self):
        """Test remote_file_copy raises ValueError for URLs with query strings."""
        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )
        # Override download_url to include a query string
        src.download_url = "http://example.com/file.bin?token=abc"

        with self.assertRaises(ValueError) as ctx:
            self.device.remote_file_copy(src)
        self.assertIn("query strings are not supported", str(ctx.exception))

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_logging_on_success(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test that transfer success is logged."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
        )

        with mock.patch("pyntc.devices.eos_device.log") as mock_log:
            self.device.remote_file_copy(src)
            self.assertTrue(
                any("transferred and verified successfully" in str(call) for call in mock_log.info.call_args_list)
            )


class TestRemoteFileCopyCommandExecution(unittest.TestCase):
    """Tests for command execution flow in remote_file_copy."""

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_command_execution_with_http(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test command execution for HTTP transfer."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        device = EOSDevice("host", "user", "pass")
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
        )

        device.remote_file_copy(src)

        mock_open.assert_called_once()
        mock_enable.assert_called_once()
        mock_ssh.send_command.assert_called()
        call_args = mock_ssh.send_command.call_args
        self.assertIn("copy http://", call_args[0][0])

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_command_execution_with_scp_credentials(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test command execution for SCP transfer with username only."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        device = EOSDevice("host", "user", "pass")
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command_timing.return_value = "Copy completed successfully"
        device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="scp://admin:password@backup.example.com/configs/startup-config",
            checksum="abc123def456",
            file_name="startup-config",
            username="admin",
            token="password",
        )

        device.remote_file_copy(src)

        mock_ssh.send_command_timing.assert_called()
        call_args = mock_ssh.send_command_timing.call_args
        self.assertIn("copy scp://", call_args[0][0])
        self.assertIn("admin@", call_args[0][0])
        self.assertNotIn("password@", call_args[0][0])

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_timeout_applied_to_send_command(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test that timeout is applied to send_command calls."""
        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        device = EOSDevice("host", "user", "pass")
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
            timeout=600,
        )

        device.remote_file_copy(src)

        mock_ssh.send_command.assert_called()
        call_args = mock_ssh.send_command.call_args
        self.assertEqual(call_args[1]["read_timeout"], 600)


class TestFileCopyModelValidation(unittest.TestCase):
    """Tests for FileCopyModel defaults and validation."""

    def test_default_timeout_value(self):
        """Test FileCopyModel default timeout is 900 seconds."""
        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
        )
        self.assertEqual(src.timeout, 900)

    def test_ftp_passive_mode_configuration(self):
        """Test FileCopyModel ftp_passive flag is set correctly."""
        for ftp_passive in [True, False]:
            with self.subTest(ftp_passive=ftp_passive):
                src = FileCopyModel(
                    download_url="ftp://admin:password@ftp.example.com/images/eos.swi",
                    checksum="abc123def456",
                    file_name="eos.swi",
                    ftp_passive=ftp_passive,
                )
                self.assertEqual(src.ftp_passive, ftp_passive)

    def test_default_ftp_passive_mode(self):
        """Test FileCopyModel default ftp_passive is True."""
        src = FileCopyModel(
            download_url="ftp://admin:password@ftp.example.com/images/eos.swi",
            checksum="abc123def456",
            file_name="eos.swi",
        )
        self.assertTrue(src.ftp_passive)

    def test_hashing_algorithm_validation(self):
        """Test FileCopyModel accepts supported hashing algorithms."""
        for algorithm in ["md5", "sha256", "sha512"]:
            with self.subTest(algorithm=algorithm):
                src = FileCopyModel(
                    download_url="http://server.example.com/file.bin",
                    checksum="abc123def456",
                    file_name="file.bin",
                    hashing_algorithm=algorithm,
                )
                self.assertEqual(src.hashing_algorithm, algorithm)

    def test_case_insensitive_algorithm_validation(self):
        """Test FileCopyModel accepts algorithms in different cases."""
        for algorithm in ["MD5", "md5", "Md5", "SHA256", "sha256", "Sha256"]:
            with self.subTest(algorithm=algorithm):
                src = FileCopyModel(
                    download_url="http://server.example.com/file.bin",
                    checksum="abc123def456",
                    file_name="file.bin",
                    hashing_algorithm=algorithm,
                )
                self.assertIn(src.hashing_algorithm.lower(), ["md5", "sha256"])


class TestFileCopyModelCredentials(unittest.TestCase):
    """Tests for FileCopyModel credential extraction."""

    def test_url_credential_extraction(self):
        """Test FileCopyModel extracts credentials from URL."""
        test_cases = [
            ("scp://admin:password@server.com/path", "admin", "password"),
            ("ftp://user:pass123@ftp.example.com/file", "user", "pass123"),
        ]
        for url, expected_username, expected_token in test_cases:
            with self.subTest(url=url):
                src = FileCopyModel(
                    download_url=url,
                    checksum="abc123def456",
                    file_name="file.bin",
                )
                self.assertEqual(src.username, expected_username)
                self.assertEqual(src.token, expected_token)

    def test_explicit_credentials_override(self):
        """Test explicit credentials take precedence over URL-embedded credentials."""
        src = FileCopyModel(
            download_url="scp://url_user:url_pass@server.com/path",
            checksum="abc123def456",
            file_name="file.bin",
            username="explicit_user",
            token="explicit_pass",
        )
        self.assertEqual(src.username, "explicit_user")
        self.assertEqual(src.token, "explicit_pass")
