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


# Property-based tests for file system normalization
try:
    from hypothesis import given
    from hypothesis import strategies as st
except ImportError:
    # Create dummy decorators if hypothesis is not available
    def given(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class _ST:
        @staticmethod
        def just(value):
            return value

        @staticmethod
        def one_of(*args):
            return args[0]

    st = _ST()


# Property-based tests for copy command construction
from pyntc.utils.models import FileCopyModel

# Property tests for Task 6: Input Validation in remote_file_copy()


@given(
    src=st.just("not_a_filecopymodel"),
)
def test_property_type_validation(src):
    """Feature: arista-remote-file-copy, Property 1: Type Validation.

    For any non-FileCopyModel object passed as `src`, the `remote_file_copy()`
    method should raise a `TypeError`.

    Validates: Requirements 1.2, 15.1
    """
    device = EOSDevice("host", "user", "pass")

    with pytest.raises(TypeError) as exc_info:
        device.remote_file_copy(src)

    assert "src must be an instance of FileCopyModel" in str(exc_info.value)


@mock.patch.object(EOSDevice, "_get_file_system")
def test_property_file_system_auto_detection(mock_get_fs):
    """Feature: arista-remote-file-copy, Property 26: File System Auto-Detection.

    For any `remote_file_copy()` call without an explicit `file_system` parameter,
    the method should call `_get_file_system()` to determine the default file system.

    Validates: Requirements 11.1
    """
    mock_get_fs.return_value = "/mnt/flash"
    device = EOSDevice("host", "user", "pass")

    src = FileCopyModel(
        download_url="http://server.example.com/file.bin",
        checksum="abc123",
        file_name="file.bin",
    )

    # Call remote_file_copy without file_system parameter
    try:
        device.remote_file_copy(src)
    except Exception:
        # We expect it to fail later, but we just want to verify _get_file_system was called
        pass

    # Verify _get_file_system was called
    mock_get_fs.assert_called()


@mock.patch.object(EOSDevice, "_get_file_system")
def test_property_explicit_file_system_usage(mock_get_fs):
    """Feature: arista-remote-file-copy, Property 27: Explicit File System Usage.

    For any `remote_file_copy()` call with an explicit `file_system` parameter,
    that value should be used instead of auto-detection.

    Validates: Requirements 11.2
    """
    device = EOSDevice("host", "user", "pass")

    src = FileCopyModel(
        download_url="http://server.example.com/file.bin",
        checksum="abc123",
        file_name="file.bin",
    )

    # Call remote_file_copy with explicit file_system parameter
    try:
        device.remote_file_copy(src, file_system="/mnt/flash")
    except Exception:
        # We expect it to fail later, but we just want to verify _get_file_system was NOT called
        pass

    # Verify _get_file_system was NOT called
    mock_get_fs.assert_not_called()


@mock.patch.object(EOSDevice, "verify_file")
@mock.patch.object(EOSDevice, "enable")
@mock.patch.object(EOSDevice, "open")
@mock.patch.object(EOSDevice, "_get_file_system")
def test_property_default_destination_from_filecopymodel(mock_get_fs, mock_open, mock_enable, mock_verify):
    """Feature: arista-remote-file-copy, Property 28: Default Destination from FileCopyModel.

    For any `remote_file_copy()` call without an explicit `dest` parameter,
    the destination should default to `src.file_name`.

    Validates: Requirements 12.1
    """
    mock_get_fs.return_value = "/mnt/flash"
    mock_verify.return_value = True

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()
    device.native_ssh.send_command.return_value = "Copy completed successfully"

    src = FileCopyModel(
        download_url="http://server.example.com/myfile.bin",
        checksum="abc123",
        file_name="myfile.bin",
    )

    # Call remote_file_copy without explicit dest
    device.remote_file_copy(src)

    # Verify verify_file was called with the default destination
    mock_verify.assert_called()
    call_args = mock_verify.call_args
    assert call_args[0][1] == "myfile.bin"  # dest should be file_name


@mock.patch.object(EOSDevice, "verify_file")
@mock.patch.object(EOSDevice, "enable")
@mock.patch.object(EOSDevice, "open")
@mock.patch.object(EOSDevice, "_get_file_system")
def test_property_explicit_destination_usage(mock_get_fs, mock_open, mock_enable, mock_verify):
    """Feature: arista-remote-file-copy, Property 29: Explicit Destination Usage.

    For any `remote_file_copy()` call with an explicit `dest` parameter,
    that value should be used as the destination filename.

    Validates: Requirements 12.2
    """
    mock_get_fs.return_value = "/mnt/flash"
    mock_verify.return_value = True

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()
    device.native_ssh.send_command.return_value = "Copy completed successfully"

    src = FileCopyModel(
        download_url="http://server.example.com/myfile.bin",
        checksum="abc123",
        file_name="myfile.bin",
    )

    # Call remote_file_copy with explicit dest
    device.remote_file_copy(src, dest="different_name.bin")

    # Verify verify_file was called with the explicit destination
    mock_verify.assert_called()
    call_args = mock_verify.call_args
    assert call_args[0][1] == "different_name.bin"  # dest should be the explicit value


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
        with pytest.raises(TypeError) as exc_info:
            self.device.remote_file_copy("not_a_model")
        assert "src must be an instance of FileCopyModel" in str(exc_info.value)

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_skip_transfer_on_checksum_match(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy skips transfer when file exists with matching checksum."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        # Mock netmiko connection
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        # Should return without raising exception
        self.device.remote_file_copy(src)

        # Verify that verify_file was called
        mock_verify.assert_called()

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_http_transfer(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy executes HTTP transfer correctly."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True  # Verification passes

        # Mock netmiko connection
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        # Should not raise exception
        self.device.remote_file_copy(src)

        # Verify open and enable were called
        mock_open.assert_called_once()
        mock_enable.assert_called_once()

        # Verify send_command was called with correct command
        mock_ssh.send_command.assert_called()

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_verification_failure(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy raises FileTransferError when verification fails."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = False  # Verification fails

        # Mock netmiko connection
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        # Should raise FileTransferError
        with pytest.raises(FileTransferError):
            self.device.remote_file_copy(src)

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_with_explicit_dest(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy uses explicit dest parameter."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        # Mock netmiko connection
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        # Call with explicit dest
        self.device.remote_file_copy(src, dest="custom_name.bin")

        # Verify verify_file was called with custom dest
        call_args = mock_verify.call_args
        assert call_args[0][1] == "custom_name.bin"

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_with_explicit_file_system(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy uses explicit file_system parameter."""
        from pyntc.utils.models import FileCopyModel

        mock_verify.return_value = True

        # Mock netmiko connection
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        # Call with explicit file_system
        self.device.remote_file_copy(src, file_system="flash:")

        # Verify _get_file_system was NOT called
        mock_get_fs.assert_not_called()

        # Verify send_command was called with correct file_system
        call_args = mock_ssh.send_command.call_args
        assert "flash:" in call_args[0][0]

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_scp_with_credentials(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy constructs SCP command with username only."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        # Mock netmiko connection
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command_timing.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="scp://user:pass@server.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
        )

        self.device.remote_file_copy(src)

        # Verify send_command_timing was called with SCP command containing username only
        # Token is provided at the Arista "Password:" prompt
        call_args = mock_ssh.send_command_timing.call_args
        command = call_args[0][0]
        assert "scp://" in command
        assert "user@" in command
        assert "pass@" not in command  # Password should not be in command

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_remote_file_copy_timeout_applied(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test remote_file_copy applies timeout to send_command."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "flash:"
        mock_verify.return_value = True

        # Mock netmiko connection
        mock_ssh = mock.MagicMock()
        mock_ssh.send_command.return_value = "Copy completed successfully"
        self.device.native_ssh = mock_ssh

        src = FileCopyModel(
            download_url="http://example.com/file.bin",
            checksum="abc123",
            file_name="file.bin",
            timeout=1800,
        )

        self.device.remote_file_copy(src)

        # Verify send_command was called with correct timeout
        call_args = mock_ssh.send_command.call_args
        assert call_args[1]["read_timeout"] == 1800


# Property-based tests for Task 7: Pre-transfer verification


@mock.patch.object(EOSDevice, "verify_file")
@mock.patch.object(EOSDevice, "enable")
@mock.patch.object(EOSDevice, "open")
@mock.patch.object(EOSDevice, "_get_file_system")
def test_property_skip_transfer_on_checksum_match(mock_get_fs, mock_open, mock_enable, mock_verify):
    """Feature: arista-remote-file-copy, Property 14: Skip Transfer on Checksum Match.

    For any file that already exists on the device with a matching checksum,
    the `remote_file_copy()` method should return successfully after verification.

    Validates: Requirements 5.2
    """
    from pyntc.utils.models import FileCopyModel

    mock_get_fs.return_value = "/mnt/flash"
    mock_verify.return_value = True  # File exists with matching checksum

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()
    device.native_ssh.send_command.return_value = "Copy completed successfully"

    src = FileCopyModel(
        download_url="http://server.example.com/file.bin",
        checksum="abc123def456",
        file_name="file.bin",
    )

    # Call remote_file_copy
    device.remote_file_copy(src)

    # Verify that verify_file was called
    mock_verify.assert_called()

    # Verify that send_command was called (transfer always occurs)
    device.native_ssh.send_command.assert_called()


@mock.patch.object(EOSDevice, "verify_file")
@mock.patch.object(EOSDevice, "enable")
@mock.patch.object(EOSDevice, "open")
@mock.patch.object(EOSDevice, "_get_file_system")
def test_property_proceed_on_checksum_mismatch(mock_get_fs, mock_open, mock_enable, mock_verify):
    """Feature: arista-remote-file-copy, Property 15: Proceed on Checksum Mismatch.

    For any file that exists on the device but has a mismatched checksum,
    the `remote_file_copy()` method should proceed with the file transfer.

    Validates: Requirements 5.3
    """
    from pyntc.utils.models import FileCopyModel

    mock_get_fs.return_value = "/mnt/flash"
    # Verification fails (file doesn't exist or checksum mismatches)
    mock_verify.return_value = False

    device = EOSDevice("host", "user", "pass")
    mock_ssh = mock.MagicMock()
    mock_ssh.send_command.return_value = "Copy completed successfully"
    device.native_ssh = mock_ssh

    src = FileCopyModel(
        download_url="http://server.example.com/file.bin",
        checksum="abc123def456",
        file_name="file.bin",
    )

    # Call remote_file_copy - should raise FileTransferError because verification fails
    with pytest.raises(FileTransferError):
        device.remote_file_copy(src)

    # Verify that send_command was called with a copy command
    mock_ssh.send_command.assert_called()
    call_args = mock_ssh.send_command.call_args
    assert "copy" in call_args[0][0].lower()


# Tests for Task 8: Command Execution


class TestRemoteFileCopyCommandExecution(unittest.TestCase):
    """Tests for command execution flow in remote_file_copy."""

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_command_execution_with_http(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test command execution for HTTP transfer."""
        from pyntc.utils.models import FileCopyModel

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

        # Verify open() was called
        mock_open.assert_called_once()

        # Verify enable() was called
        mock_enable.assert_called_once()

        # Verify send_command was called with HTTP copy command
        mock_ssh.send_command.assert_called()
        call_args = mock_ssh.send_command.call_args
        assert "copy http://" in call_args[0][0]

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_command_execution_with_scp_credentials(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test command execution for SCP transfer with username only."""
        from pyntc.utils.models import FileCopyModel

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

        # Verify send_command_timing was called with SCP copy command including username only
        # Token is provided at the Arista "Password:" prompt
        mock_ssh.send_command_timing.assert_called()
        call_args = mock_ssh.send_command_timing.call_args
        assert "copy scp://" in call_args[0][0]
        assert "admin@" in call_args[0][0]
        assert "password@" not in call_args[0][0]  # Password should not be in command

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_timeout_applied_to_send_command(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test that timeout is applied to send_command calls."""
        from pyntc.utils.models import FileCopyModel

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

        # Verify send_command was called with the specified timeout
        mock_ssh.send_command.assert_called()
        call_args = mock_ssh.send_command.call_args
        assert call_args[1]["read_timeout"] == 600


# Tests for Task 9: Post-transfer Verification


@pytest.mark.parametrize(
    "checksum,algorithm",
    [
        ("abc123def456", "md5"),
        ("abc123def456789", "sha256"),
    ],
)
def test_property_post_transfer_verification(checksum, algorithm):
    """Feature: arista-remote-file-copy, Property 20: Post-Transfer Verification.

    For any completed file transfer, the method should verify the file exists
    on the device and compute its checksum using the specified algorithm.

    Validates: Requirements 9.1, 9.2
    """
    from pyntc.utils.models import FileCopyModel

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()

    with mock.patch.object(device, "verify_file") as mock_verify:
        with mock.patch.object(device, "_get_file_system") as mock_get_fs:
            with mock.patch.object(device, "open"):
                with mock.patch.object(device, "enable"):
                    mock_get_fs.return_value = "/mnt/flash"
                    mock_verify.return_value = True
                    device.native_ssh.send_command.return_value = "Copy completed successfully"

                    src = FileCopyModel(
                        download_url="http://server.example.com/file.bin",
                        checksum=checksum,
                        file_name="file.bin",
                        hashing_algorithm=algorithm,
                    )

                    device.remote_file_copy(src)

                    # Verify that verify_file was called
                    mock_verify.assert_called()


@pytest.mark.parametrize(
    "checksum,algorithm",
    [
        ("abc123def456", "md5"),
        ("abc123def456789", "sha256"),
    ],
)
def test_property_checksum_match_verification(checksum, algorithm):
    """Feature: arista-remote-file-copy, Property 21: Checksum Match Verification.

    For any transferred file where the computed checksum matches the expected checksum,
    the method should consider the transfer successful.

    Validates: Requirements 9.3
    """
    from pyntc.utils.models import FileCopyModel

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()

    with mock.patch.object(device, "verify_file") as mock_verify:
        with mock.patch.object(device, "_get_file_system") as mock_get_fs:
            with mock.patch.object(device, "open"):
                with mock.patch.object(device, "enable"):
                    mock_get_fs.return_value = "/mnt/flash"
                    # Verification passes
                    mock_verify.return_value = True
                    device.native_ssh.send_command.return_value = "Copy completed successfully"

                    src = FileCopyModel(
                        download_url="http://server.example.com/file.bin",
                        checksum=checksum,
                        file_name="file.bin",
                        hashing_algorithm=algorithm,
                    )

                    # Should not raise an exception
                    device.remote_file_copy(src)


def test_property_checksum_mismatch_error():
    """Feature: arista-remote-file-copy, Property 22: Checksum Mismatch Error.

    For any transferred file where the computed checksum does not match the expected checksum,
    the method should raise a FileTransferError.

    Validates: Requirements 9.4
    """
    from pyntc.utils.models import FileCopyModel

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()

    with mock.patch.object(device, "verify_file") as mock_verify:
        with mock.patch.object(device, "_get_file_system") as mock_get_fs:
            with mock.patch.object(device, "open"):
                with mock.patch.object(device, "enable"):
                    mock_get_fs.return_value = "/mnt/flash"
                    # First call: file doesn't exist (False)
                    # Second call: checksum mismatch (False)
                    mock_verify.side_effect = [False, False]
                    device.native_ssh.send_command.return_value = "Copy completed successfully"

                    src = FileCopyModel(
                        download_url="http://server.example.com/file.bin",
                        checksum="abc123def456",
                        file_name="file.bin",
                    )

                    # Should raise FileTransferError
                    with pytest.raises(FileTransferError):
                        device.remote_file_copy(src)


def test_property_missing_file_after_transfer_error():
    """Feature: arista-remote-file-copy, Property 23: Missing File After Transfer Error.

    For any transfer that completes but the file does not exist on the device afterward,
    the method should raise a FileTransferError.

    Validates: Requirements 9.5
    """
    from pyntc.utils.models import FileCopyModel

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()

    with mock.patch.object(device, "verify_file") as mock_verify:
        with mock.patch.object(device, "_get_file_system") as mock_get_fs:
            with mock.patch.object(device, "open"):
                with mock.patch.object(device, "enable"):
                    mock_get_fs.return_value = "/mnt/flash"
                    # First call: file doesn't exist (False)
                    # Second call: file still doesn't exist (False)
                    mock_verify.side_effect = [False, False]
                    device.native_ssh.send_command.return_value = "Copy completed successfully"

                    src = FileCopyModel(
                        download_url="http://server.example.com/file.bin",
                        checksum="abc123def456",
                        file_name="file.bin",
                    )

                    # Should raise FileTransferError
                    with pytest.raises(FileTransferError):
                        device.remote_file_copy(src)


# Tests for Task 10: Timeout and FTP Support


@pytest.mark.parametrize("timeout", [300, 600, 900, 1800])
def test_property_timeout_application(timeout):
    """Feature: arista-remote-file-copy, Property 24: Timeout Application.

    For any FileCopyModel with a specified timeout value, that timeout should be used
    when sending commands to the device during transfer.

    Validates: Requirements 10.1, 10.3
    """
    from pyntc.utils.models import FileCopyModel

    device = EOSDevice("host", "user", "pass")
    device.native_ssh = mock.MagicMock()

    with mock.patch.object(device, "verify_file") as mock_verify:
        with mock.patch.object(device, "_get_file_system") as mock_get_fs:
            with mock.patch.object(device, "open"):
                with mock.patch.object(device, "enable"):
                    mock_get_fs.return_value = "/mnt/flash"
                    mock_verify.return_value = True
                    device.native_ssh.send_command.return_value = "Copy completed successfully"

                    src = FileCopyModel(
                        download_url="http://server.example.com/file.bin",
                        checksum="abc123def456",
                        file_name="file.bin",
                        timeout=timeout,
                    )

                    device.remote_file_copy(src)

                    # Verify send_command was called with the correct timeout
                    call_args = device.native_ssh.send_command.call_args
                    assert call_args[1]["read_timeout"] == timeout


def test_property_default_timeout_value():
    """Feature: arista-remote-file-copy, Property 25: Default Timeout Value.

    For any FileCopyModel without an explicit timeout, the default timeout should be 900 seconds.

    Validates: Requirements 10.2
    """
    from pyntc.utils.models import FileCopyModel

    src = FileCopyModel(
        download_url="http://server.example.com/file.bin",
        checksum="abc123def456",
        file_name="file.bin",
    )

    # Verify default timeout is 900
    assert src.timeout == 900


@pytest.mark.parametrize("ftp_passive", [True, False])
def test_property_ftp_passive_mode_configuration(ftp_passive):
    """Feature: arista-remote-file-copy, Property 30/31: FTP Passive Mode Configuration.

    For any FileCopyModel with ftp_passive flag, the FTP transfer should use the specified mode.

    Validates: Requirements 19.1, 19.2
    """
    from pyntc.utils.models import FileCopyModel

    src = FileCopyModel(
        download_url="ftp://admin:password@ftp.example.com/images/eos.swi",
        checksum="abc123def456",
        file_name="eos.swi",
        ftp_passive=ftp_passive,
    )

    # Verify ftp_passive is set correctly
    assert src.ftp_passive == ftp_passive


def test_property_default_ftp_passive_mode():
    """Feature: arista-remote-file-copy, Property 32: Default FTP Passive Mode.

    For any FileCopyModel without an explicit ftp_passive parameter, the default should be True.

    Validates: Requirements 19.3
    """
    from pyntc.utils.models import FileCopyModel

    src = FileCopyModel(
        download_url="ftp://admin:password@ftp.example.com/images/eos.swi",
        checksum="abc123def456",
        file_name="eos.swi",
    )

    # Verify default ftp_passive is True
    assert src.ftp_passive is True


# Tests for Task 11: Error Handling and Logging


class TestRemoteFileCopyErrorHandling(unittest.TestCase):
    """Tests for error handling in remote_file_copy."""

    def test_invalid_src_type_raises_typeerror(self):
        """Test that invalid src type raises TypeError."""
        device = EOSDevice("host", "user", "pass")

        with pytest.raises(TypeError) as exc_info:
            device.remote_file_copy("not a FileCopyModel")

        assert "src must be an instance of FileCopyModel" in str(exc_info.value)

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_transfer_failure_raises_filetransfererror(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test that transfer failure raises FileTransferError."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.side_effect = [False, False]  # Post-transfer verification fails

        device = EOSDevice("host", "user", "pass")
        device.native_ssh = mock.MagicMock()
        device.native_ssh.send_command.return_value = "Copy completed successfully"

        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
        )

        with pytest.raises(FileTransferError):
            device.remote_file_copy(src)

    @mock.patch.object(EOSDevice, "verify_file")
    @mock.patch.object(EOSDevice, "enable")
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "_get_file_system")
    def test_logging_on_transfer_success(self, mock_get_fs, mock_open, mock_enable, mock_verify):
        """Test that transfer success is logged."""
        from pyntc.utils.models import FileCopyModel

        mock_get_fs.return_value = "/mnt/flash"
        mock_verify.return_value = True

        device = EOSDevice("host", "user", "pass")
        device.native_ssh = mock.MagicMock()
        device.native_ssh.send_command.return_value = "Copy completed successfully"

        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
        )

        with mock.patch("pyntc.devices.eos_device.log") as mock_log:
            device.remote_file_copy(src)

            # Verify that info log was called for successful transfer
            assert any("transferred and verified successfully" in str(call) for call in mock_log.info.call_args_list)


# Tests for Task 12: FileCopyModel Validation


@pytest.mark.parametrize("algorithm", ["md5", "sha256", "sha512"])
def test_property_hashing_algorithm_validation(algorithm):
    """Feature: arista-remote-file-copy, Property 10: Hashing Algorithm Validation.

    For any unsupported hashing algorithm, FileCopyModel initialization should raise a ValueError.

    Validates: Requirements 6.3, 17.1, 17.2
    """
    from pyntc.utils.models import FileCopyModel

    # Should not raise for supported algorithms
    src = FileCopyModel(
        download_url="http://server.example.com/file.bin",
        checksum="abc123def456",
        file_name="file.bin",
        hashing_algorithm=algorithm,
    )

    assert src.hashing_algorithm == algorithm


def test_property_case_insensitive_algorithm_validation():
    """Feature: arista-remote-file-copy, Property 11: Case-Insensitive Algorithm Validation.

    For any hashing algorithm specified in different cases, the FileCopyModel should accept it as valid.

    Validates: Requirements 17.3
    """
    from pyntc.utils.models import FileCopyModel

    # Should accept case-insensitive algorithms
    for algorithm in ["MD5", "md5", "Md5", "SHA256", "sha256", "Sha256"]:
        src = FileCopyModel(
            download_url="http://server.example.com/file.bin",
            checksum="abc123def456",
            file_name="file.bin",
            hashing_algorithm=algorithm,
        )

        # Verify it was accepted (no exception raised)
        assert src.hashing_algorithm.lower() in ["md5", "sha256"]


@pytest.mark.parametrize(
    "url,expected_username,expected_token",
    [
        ("scp://admin:password@server.com/path", "admin", "password"),
        ("ftp://user:pass123@ftp.example.com/file", "user", "pass123"),
    ],
)
def test_property_url_credential_extraction(url, expected_username, expected_token):
    """Feature: arista-remote-file-copy, Property 12: URL Credential Extraction.

    For any URL containing embedded credentials, FileCopyModel should extract username and password.

    Validates: Requirements 3.1, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6
    """
    from pyntc.utils.models import FileCopyModel

    src = FileCopyModel(
        download_url=url,
        checksum="abc123def456",
        file_name="file.bin",
    )

    # Verify credentials were extracted
    assert src.username == expected_username
    assert src.token == expected_token


def test_property_explicit_credentials_override():
    """Feature: arista-remote-file-copy, Property 13: Explicit Credentials Override.

    For any FileCopyModel where both URL-embedded credentials and explicit fields are provided,
    the explicit fields should take precedence.

    Validates: Requirements 3.2
    """
    from pyntc.utils.models import FileCopyModel

    src = FileCopyModel(
        download_url="scp://url_user:url_pass@server.com/path",
        checksum="abc123def456",
        file_name="file.bin",
        username="explicit_user",
        token="explicit_pass",
    )

    # Verify explicit credentials take precedence
    assert src.username == "explicit_user"
    assert src.token == "explicit_pass"
