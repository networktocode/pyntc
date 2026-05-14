import unittest

import mock
from hypothesis import given
from hypothesis import strategies as st

from pyntc.devices.base_device import RollbackError
from pyntc.devices.nxos_device import NXOSDevice
from pyntc.devices.pynxos.errors import CLIError
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    FileTransferError,
    NotEnoughFreeSpaceError,
    NTCFileNotFoundError,
)
from pyntc.utils.models import FileCopyModel

from .device_mocks.nxos import show, show_list

BOOT_IMAGE = "n9000-dk9.9.2.1.bin"
KICKSTART_IMAGE = "n9000-kickstart.9.2.1.bin"
FILE_SYSTEM = "bootflash:"
DEVICE_FACTS = {
    "uptime_string": "13:01:08:06",
    "uptime": 1127286,
    "vlans": ["1", "2", "3", "4", "5"],
    "os_version": "7.0(3)I2(1)",
    "serial_number": "SAL1819S6LU",
    "model": "Nexus9000 C9396PX Chassis",
    "hostname": "n9k1",
    "interfaces": ["mgmt0", "Ethernet1/1", "Ethernet1/2", "Ethernet1/3"],
    "fqdn": "N/A",
}


class TestNXOSDevice(unittest.TestCase):
    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    @mock.patch("pyntc.devices.pynxos.device.Device.facts", new_callable=mock.PropertyMock)
    def setUp(self, mock_facts, mock_device, mock_connect_handler):
        self.mock_native_ssh = mock_connect_handler.return_value
        self.device = NXOSDevice("host", "user", "pass")
        mock_device.show.side_effect = show
        mock_device.show_list.side_effect = show_list
        mock_facts.return_value = DEVICE_FACTS

        self.device.native = mock_device
        self.device.native_ssh = self.mock_native_ssh
        self.device.native._facts = {}
        type(self.device.native).facts = mock_facts.return_value

    def test_config(self):
        command = "interface eth 1/1"
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with(command)

    def test_bad_config(self):
        command = "asdf poknw"
        self.device.native.config.side_effect = CLIError(command, "Invalid command.")

        with self.assertRaisesRegex(CommandError, command):
            self.device.config(command)

    def test_config_list(self):
        commands = ["interface eth 1/1", "no shutdown"]
        result = self.device.config(commands)

        self.assertIsNone(result)
        self.device.native.config_list.assert_called_with(commands)

    def test_bad_config_list(self):
        commands = ["interface Eth1", "apons"]
        self.device.native.config_list.side_effect = CLIError(commands[1], "Invalid command.")

        with self.assertRaisesRegex(CommandListError, commands[1]):
            self.device.config(commands)

    def test_show(self):
        command = "show cdp neighbors"
        result = self.device.show(command)

        self.assertIsInstance(result, dict)
        self.assertIsInstance(result.get("neigh_count"), int)

        self.device.native.show.assert_called_with(command, raw_text=False)

    def test_bad_show(self):
        command = "show microsoft"
        with self.assertRaises(CommandError):
            self.device.show(command)

    def test_show_raw_text(self):
        command = "show hostname"
        result = self.device.show(command, raw_text=True)

        self.assertIsInstance(result, str)
        self.assertEqual(result, "n9k1.cisconxapi.com")
        self.device.native.show.assert_called_with(command, raw_text=True)

    def test_show_list(self):
        commands = ["show hostname", "show clock"]

        result = self.device.show(commands)
        self.assertIsInstance(result, list)

        self.assertIn("hostname", result[0])
        self.assertIn("simple_time", result[1])

        self.device.native.show_list.assert_called_with(commands, raw_text=False)

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        with self.assertRaisesRegex(CommandListError, "show badcommand"):
            self.device.show(commands)

    def test_save(self):
        result = self.device.save()
        self.device.native.save.return_value = True

        self.assertTrue(result)
        self.device.native.save.assert_called_with(filename="startup-config")

    def test_file_copy_remote_exists(self):
        self.device.native.file_copy_remote_exists.return_value = True
        result = self.device.file_copy_remote_exists("source_file", "dest_file")

        self.assertTrue(result)
        self.device.native.file_copy_remote_exists.assert_called_with(
            "source_file", "dest_file", file_system=FILE_SYSTEM
        )

    def test_file_copy_remote_exists_failure(self):
        self.device.native.file_copy_remote_exists.return_value = False
        result = self.device.file_copy_remote_exists("source_file", "dest_file")

        self.assertFalse(result)
        self.device.native.file_copy_remote_exists.assert_called_with(
            "source_file", "dest_file", file_system=FILE_SYSTEM
        )

    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024 * 1024 * 1024)
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024)
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, True])
    def test_file_copy(self, mock_fcre, mock_getsize, mock_get_free_space):
        self.device.file_copy("source_file", "dest_file")
        self.device.native.file_copy.assert_called_with("source_file", "dest_file", file_system=FILE_SYSTEM)
        self.device.native.file_copy.assert_called()

    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024 * 1024 * 1024)
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024)
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, True])
    def test_file_copy_no_dest(self, mock_fcre, mock_getsize, mock_get_free_space):
        self.device.file_copy("source_file")
        self.device.native.file_copy.assert_called_with("source_file", "source_file", file_system=FILE_SYSTEM)
        self.device.native.file_copy.assert_called()

    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[True])
    def test_file_copy_file_exists(self, mock_fcre):
        self.device.file_copy("source_file", "dest_file")
        self.device.native.file_copy.assert_not_called()

    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024 * 1024 * 1024)
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024)
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, False])
    def test_file_copy_fail(self, mock_fcre, mock_getsize, mock_get_free_space):
        with self.assertRaises(FileTransferError):
            self.device.file_copy("source_file")
        self.device.native.file_copy.assert_called()

    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024)  # Only 1KB free
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024 * 1024)  # Trying to copy 1MB
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False])
    def test_file_copy_raises_not_enough_free_space(self, mock_fcre, mock_getsize, mock_get_free_space):
        """Test file_copy raises NotEnoughFreeSpaceError when insufficient space."""
        with self.assertRaises(NotEnoughFreeSpaceError):
            self.device.file_copy("source_file")

    def test_reboot(self):
        self.device.reboot()
        self.device.native.show_list.assert_called_with(["terminal dont-ask", "reload"])
        # self.device.native.reboot.assert_called_with(confirm=True)

    def test_boot_options(self):
        expected = {"sys": "my_sys", "boot": "my_boot"}
        self.device.native.get_boot_options.return_value = expected
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, expected)

    def test_set_boot_options(self):
        self.device.set_boot_options(BOOT_IMAGE)
        self.device.native.set_boot_options.assert_called_with(
            f"{FILE_SYSTEM}{BOOT_IMAGE}", kickstart=None, reboot=True
        )

    def test_set_boot_options_dir(self):
        self.device.set_boot_options(BOOT_IMAGE, file_system=FILE_SYSTEM)
        self.device.native.set_boot_options.assert_called_with(
            f"{FILE_SYSTEM}{BOOT_IMAGE}", kickstart=None, reboot=True
        )

    def test_set_boot_options_kickstart(self):
        self.device.set_boot_options(BOOT_IMAGE, kickstart=KICKSTART_IMAGE)
        self.device.native.set_boot_options.assert_called_with(
            f"{FILE_SYSTEM}{BOOT_IMAGE}", kickstart=f"{FILE_SYSTEM}{KICKSTART_IMAGE}", reboot=True
        )

    @mock.patch.object(NXOSDevice, "show", return_value=FILE_SYSTEM)
    def test_set_boot_options_no_file(self, mock_show):
        with self.assertRaises(NTCFileNotFoundError) as no_file:
            self.device.set_boot_options(BOOT_IMAGE)
        self.assertIn(f"{BOOT_IMAGE} was not found in {FILE_SYSTEM}", no_file.exception.message)

    @mock.patch.object(NXOSDevice, "show", return_value=f"{FILE_SYSTEM}\n{BOOT_IMAGE}")
    def test_set_boot_options_no_kickstart(self, mock_show):
        with self.assertRaises(NTCFileNotFoundError) as no_file:
            self.device.set_boot_options(BOOT_IMAGE, kickstart=KICKSTART_IMAGE)
        self.assertIn(f"{KICKSTART_IMAGE} was not found in {FILE_SYSTEM}", no_file.exception.message)

    def test_backup_running_config(self):
        filename = "local_running_config"
        self.device.backup_running_config(filename)

        self.device.native.backup_running_config.assert_called_with(filename)

    def test_rollback(self):
        self.device.rollback("good_checkpoint")
        self.device.native.rollback.assert_called_with("good_checkpoint")

    def test_bad_rollback(self):
        self.device.native.rollback.side_effect = CLIError("rollback", "bad rollback command")

        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpiont(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.checkpoint.assert_called_with("good_checkpoint")

    def test_uptime(self):
        uptime = self.device.uptime
        assert uptime == 1127286

    def test_vendor(self):
        vendor = self.device.vendor
        assert vendor == "cisco"

    def test_os_version(self):
        os_version = self.device.os_version
        assert os_version == "7.0(3)I2(1)"

    def test_interfaces(self):
        interfaces = self.device.interfaces
        assert interfaces == ["mgmt0", "Ethernet1/1", "Ethernet1/2", "Ethernet1/3"]

    def test_hostname(self):
        hostname = self.device.hostname
        assert hostname == "n9k1"

    def test_fqdn(self):
        fqdn = self.device.fqdn
        assert fqdn == "N/A"

    def test_serial_number(self):
        serial_number = self.device.serial_number
        assert serial_number == "SAL1819S6LU"

    def test_model(self):
        model = self.device.model
        assert model == "Nexus9000 C9396PX Chassis"

    @mock.patch("pyntc.devices.pynxos.device.Device.running_config", new_callable=mock.PropertyMock)
    def test_running_config(self, mock_rc):
        type(self.device.native).running_config = mock_rc
        self.device.running_config()
        self.device.native.running_config.assert_called_with()

    def test_starting_config(self):
        expected = self.device.show("show startup-config", raw_text=True)
        self.assertEqual(self.device.startup_config, expected)

    def test_refresh(self):
        self.assertTrue(hasattr(self.device.native, "_facts"))
        self.device.refresh()
        self.assertIsNone(self.device._uptime)
        self.assertFalse(hasattr(self.device.native, "_facts"))

    def test_get_file_system(self):
        self.device.native_ssh.send_command.return_value = "bootflash:"
        self.assertEqual(self.device._get_file_system(), "bootflash:")
        self.device.native_ssh.send_command.assert_called_with("dir", read_timeout=30)

    def test_get_file_system_not_found(self):
        self.device.native_ssh.send_command.return_value = "no filesystems here"
        with self.assertRaises(FileSystemNotFoundError):
            self.device._get_file_system()
        self.device.native_ssh.send_command.assert_called_with("dir", read_timeout=30)

    def test_get_free_space(self):
        """Test _get_free_space parses NXOS dir output correctly."""
        # NXOS dir output format with free space at the end
        self.device.native_ssh.send_command.return_value = """Directory of bootflash:/
4096         Mar 03 22:47:15 2026  .rpmstore/
4733329408   bytes used
47171194880  bytes free
51904524288  bytes total

"""
        result = self.device._get_free_space()
        self.assertEqual(result, 47171194880)
        # Should call _get_file_system (which uses SSH) and then dir command via SSH
        ssh_calls = self.device.native_ssh.send_command.call_args_list
        self.assertTrue(any("dir" in str(call) for call in ssh_calls))

    def test_get_free_space_with_custom_filesystem(self):
        """Test _get_free_space uses custom file system when provided."""
        self.device.native_ssh.send_command.return_value = """Directory of disk0:/
1000000      bytes used
2000000      bytes free
3000000      bytes total

"""
        result = self.device._get_free_space("disk0:")
        self.assertEqual(result, 2000000)
        self.device.native_ssh.send_command.assert_called_with("dir disk0:", read_timeout=30)

    def test_get_free_space_raises_on_parse_error(self):
        """Test _get_free_space raises CommandError when output can't be parsed."""
        self.device.native_ssh.send_command.return_value = "Directory of bootflash:/\nNo free space info here\n"
        with self.assertRaises(CommandError):
            self.device._get_free_space()

    def test_check_file_exists_true(self):
        self.device.native_ssh.send_command.return_value = "12345 bootflash:/nxos.bin"
        result = self.device.check_file_exists("nxos.bin", file_system="bootflash:")
        self.assertTrue(result)
        self.device.native_ssh.send_command.assert_called_with("dir bootflash:/nxos.bin", read_timeout=30)

    def test_check_file_exists_false(self):
        self.device.native_ssh.send_command.return_value = "No such file or directory"
        result = self.device.check_file_exists("nxos.bin", file_system="bootflash:")
        self.assertFalse(result)
        self.device.native_ssh.send_command.assert_called_with("dir bootflash:/nxos.bin", read_timeout=30)

    def test_check_file_exists_command_error(self):
        self.device.native_ssh.send_command.return_value = "some ambiguous output"
        with self.assertRaises(CommandError):
            self.device.check_file_exists("nxos.bin", file_system="bootflash:")

    def test_get_remote_checksum(self):
        self.device.native_ssh.send_command.return_value = "abc123"
        result = self.device.get_remote_checksum("nxos.bin", hashing_algorithm="md5", file_system="bootflash:")
        self.assertEqual(result, "abc123")
        self.device.native_ssh.send_command.assert_called_with("show file bootflash:/nxos.bin md5sum", read_timeout=30)

    def test_get_remote_checksum_invalid_algorithm(self):
        with self.assertRaises(ValueError):
            self.device.get_remote_checksum("nxos.bin", hashing_algorithm="sha1", file_system="bootflash:")

    def test_verify_file_true(self):
        with (
            mock.patch.object(NXOSDevice, "check_file_exists", return_value=True),
            mock.patch.object(NXOSDevice, "get_remote_checksum", return_value="abc123"),
        ):
            result = self.device.verify_file("abc123", "nxos.bin", file_system="bootflash:")
            self.assertTrue(result)

    def test_verify_file_false(self):
        with (
            mock.patch.object(NXOSDevice, "check_file_exists", return_value=True),
            mock.patch.object(NXOSDevice, "get_remote_checksum", return_value="different"),
        ):
            result = self.device.verify_file("abc123", "nxos.bin", file_system="bootflash:")
            self.assertFalse(result)

    def test_remote_file_copy_existing_verified_file(self):
        src = FileCopyModel(
            download_url="http://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
        )
        with mock.patch.object(NXOSDevice, "verify_file", return_value=True) as verify_mock:
            self.device.remote_file_copy(src, file_system="bootflash:")
            verify_mock.assert_called_once_with("abc123", "nxos.bin", hashing_algorithm="md5", file_system="bootflash:")
            self.device.native_ssh.send_command.assert_not_called()

    def test_remote_file_copy_transfer_success(self):
        src = FileCopyModel(
            download_url="http://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
        )
        self.device.native_ssh.find_prompt.return_value = "host#"
        # Mock send_command to return success message that includes the prompt
        self.device.native_ssh.send_command.return_value = "Copy complete\nhost#"
        with mock.patch.object(NXOSDevice, "verify_file", side_effect=[False, True]):
            self.device.remote_file_copy(src, file_system="bootflash:")
        # Verify send_command was called with expect_string parameter
        self.device.native_ssh.send_command.assert_called_once()
        call_args = self.device.native_ssh.send_command.call_args
        self.assertIn("expect_string", call_args.kwargs)

    def test_remote_file_copy_transfer_fails_verification(self):
        src = FileCopyModel(
            download_url="http://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
        )
        self.device.native_ssh.find_prompt.return_value = "host#"
        # Mock send_command to return success message that includes the prompt
        self.device.native_ssh.send_command.return_value = "Copy complete\nhost#"
        with mock.patch.object(NXOSDevice, "verify_file", side_effect=[False, False]):
            with self.assertRaises(FileTransferError):
                self.device.remote_file_copy(src, file_system="bootflash:")

    @mock.patch.object(NXOSDevice, "verify_file", return_value=False)
    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024)  # Only 1KB free
    def test_remote_file_copy_raises_not_enough_free_space(self, mock_get_free_space, mock_verify):
        """Test remote_file_copy raises NotEnoughFreeSpaceError when insufficient space."""
        src = FileCopyModel(
            download_url="http://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
            file_size=1024 * 1024,  # Trying to copy 1MB
        )
        self.device.native_ssh.find_prompt.return_value = "host#"
        with self.assertRaises(NotEnoughFreeSpaceError):
            self.device.remote_file_copy(src, file_system="bootflash:")
        self.device.native_ssh.send_command.assert_not_called()

    def test_remote_file_copy_with_vrf_prompt_handling(self):
        """Test remote_file_copy handles VRF prompts correctly."""
        src = FileCopyModel(
            download_url="ftp://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
            username="testuser",
            token="testpass",
            vrf="management",  # VRF specified for prompt response
        )
        self.device.native_ssh.find_prompt.return_value = "host#"
        # Mock send_command to return success message that includes the prompt
        self.device.native_ssh.send_command.return_value = "Copy complete\nhost#"
        with mock.patch.object(NXOSDevice, "verify_file", side_effect=[False, True]):
            self.device.remote_file_copy(src, file_system="bootflash:")

        # Verify send_command was called with VRF prompt handling
        self.device.native_ssh.send_command.assert_called_once()
        call_args = self.device.native_ssh.send_command.call_args
        self.assertIn("expect_string", call_args.kwargs)
        # Verify the expect_string contains VRF prompt pattern
        expect_string = call_args.kwargs["expect_string"]
        self.assertIn("Enter vrf", expect_string)

    def test_remote_file_copy_with_no_vrf_specified(self):
        """Test remote_file_copy handles VRF prompts when no VRF is specified."""
        src = FileCopyModel(
            download_url="ftp://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
            username="testuser",
            token="testpass",
            # No VRF specified - should respond with empty string to VRF prompt
        )
        self.device.native_ssh.find_prompt.return_value = "host#"
        # Mock send_command to return success message that includes the prompt
        self.device.native_ssh.send_command.return_value = "Copy complete\nhost#"
        with mock.patch.object(NXOSDevice, "verify_file", side_effect=[False, True]):
            self.device.remote_file_copy(src, file_system="bootflash:")

        # Verify send_command was called with VRF prompt handling
        self.device.native_ssh.send_command.assert_called_once()
        call_args = self.device.native_ssh.send_command.call_args
        self.assertIn("expect_string", call_args.kwargs)
        # Verify the expect_string contains VRF prompt pattern
        expect_string = call_args.kwargs["expect_string"]
        self.assertIn("Enter vrf", expect_string)

    def test_remote_file_copy_invalid_scheme(self):
        src = FileCopyModel(
            download_url="smtp://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
        )
        with self.assertRaises(ValueError):
            self.device.remote_file_copy(src, file_system="bootflash:")

    def test_remote_file_copy_query_string_not_supported(self):
        src = FileCopyModel(
            download_url="https://example.com/nxos.bin?token=foo",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
        )
        with self.assertRaises(ValueError):
            self.device.remote_file_copy(src, file_system="bootflash:")

    @given(
        scheme=st.sampled_from(["http", "https", "scp", "sftp", "ftp", "tftp"]),
        hostname=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"))),
        filename=st.text(
            min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "Pd"))
        ),
        checksum=st.text(min_size=32, max_size=32, alphabet=st.characters(whitelist_categories=("Ll", "Nd"))),
    )
    def test_remote_file_copy_uses_ssh_for_filesystem_detection(self, scheme, hostname, filename, checksum):
        """Property-based test: remote_file_copy should use SSH for _get_file_system calls.

        This test verifies that the SSH/HTTP protocol mismatch bug is fixed by ensuring
        that _get_file_system always uses SSH for file system operations.
        """
        src = FileCopyModel(
            download_url=f"{scheme}://{hostname}/{filename}",
            checksum=checksum,
            file_name=filename,
            hashing_algorithm="md5",
            timeout=30,
        )

        # Mock SSH operations to simulate successful file system detection
        self.device.native_ssh.send_command.return_value = "Directory of bootflash:/\n47171194880 bytes free"
        self.device.native_ssh.find_prompt.return_value = "host#"

        # Mock verify_file to return True (file already exists and verified)
        with mock.patch.object(NXOSDevice, "verify_file", return_value=True):
            # This should complete without attempting HTTP connections
            self.device.remote_file_copy(src)

        # Verify that SSH was used for directory command (filesystem detection)
        ssh_calls = self.device.native_ssh.send_command.call_args_list
        self.assertTrue(
            any("dir" in str(call) for call in ssh_calls), "Expected SSH 'dir' command for filesystem detection"
        )

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_api_port_default(self, mock_device, mock_connect_handler):
        """Test that api_port defaults to 80."""
        _ = NXOSDevice("host", "user", "pass")

        # Verify NXOSNative was called with default api_port (80)
        mock_device.assert_called_with(
            "host",
            "user",
            "pass",
            transport="http",
            timeout=30,
            port=80,  # Default api_port
            verify=True,
        )

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_api_port_custom(self, mock_device, mock_connect_handler):
        """Test that custom api_port is passed to NXOSNative."""
        _ = NXOSDevice("host", "user", "pass", api_port=8080)

        # Verify NXOSNative was called with custom api_port
        mock_device.assert_called_with(
            "host",
            "user",
            "pass",
            transport="http",
            timeout=30,
            port=8080,  # Custom api_port
            verify=True,
        )

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_api_port_with_https(self, mock_device, mock_connect_handler):
        """Test that api_port works with HTTPS transport."""
        _ = NXOSDevice("host", "user", "pass", transport="https", api_port=8443)

        # Verify NXOSNative was called with HTTPS and custom api_port
        mock_device.assert_called_with(
            "host",
            "user",
            "pass",
            transport="https",
            timeout=30,
            port=8443,  # Custom HTTPS api_port
            verify=True,
        )

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_port_parameter_preserved(self, mock_device, mock_connect_handler):
        """Test that the port parameter is preserved for future SSH port customization."""
        device = NXOSDevice("host", "user", "pass", api_port=8080, port=2222)

        # Verify api_port is used for NXOSNative (NX-API)
        mock_device.assert_called_with(
            "host",
            "user",
            "pass",
            transport="http",
            timeout=30,
            port=8080,  # api_port for NX-API
            verify=True,
        )

        # Verify port parameter is stored for future SSH use
        self.assertEqual(device.port, 2222)

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_backward_compatibility_no_api_port(self, mock_device, mock_connect_handler):
        """Test backward compatibility when api_port is not specified."""
        # Create device without specifying api_port
        _ = NXOSDevice("host", "user", "pass", transport="http")

        # Should default to port 80 for HTTP
        mock_device.assert_called_with(
            "host",
            "user",
            "pass",
            transport="http",
            timeout=30,
            port=80,  # Default api_port for HTTP
            verify=True,
        )


if __name__ == "__main__":
    unittest.main()
