import unittest
import warnings

import mock

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

        self.assertTrue(result)
        self.mock_native_ssh.send_command_timing.assert_any_call("copy running-config startup-config")
        self.mock_native_ssh.send_command_timing.assert_any_call("\n", read_timeout=200)
        self.mock_native_ssh.find_prompt.assert_called()

    def test_save_custom_filename(self):
        result = self.device.save("my-backup")

        self.assertTrue(result)
        self.mock_native_ssh.send_command_timing.assert_any_call("copy running-config my-backup")

    def test_save_reopens_when_disconnected(self):
        self.device._connected = False

        with mock.patch.object(NXOSDevice, "open") as mock_open:
            self.device.save()

        mock_open.assert_called()

    @mock.patch.object(NXOSDevice, "verify_file", return_value=True)
    @mock.patch.object(NXOSDevice, "get_local_checksum", return_value="abc123")
    def test_file_copy_remote_exists(self, mock_local_checksum, mock_verify):
        result = self.device.file_copy_remote_exists("source_file", "dest_file")

        self.assertTrue(result)
        mock_local_checksum.assert_called_with("source_file")
        mock_verify.assert_called_with("abc123", "dest_file", file_system=FILE_SYSTEM)

    @mock.patch.object(NXOSDevice, "verify_file", return_value=False)
    @mock.patch.object(NXOSDevice, "get_local_checksum", return_value="abc123")
    def test_file_copy_remote_exists_failure(self, mock_local_checksum, mock_verify):
        result = self.device.file_copy_remote_exists("source_file", "dest_file")

        self.assertFalse(result)
        mock_verify.assert_called_with("abc123", "dest_file", file_system=FILE_SYSTEM)

    @mock.patch("pyntc.devices.nxos_device.file_transfer")
    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024 * 1024 * 1024)
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024)
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, True])
    def test_file_copy(self, mock_fcre, mock_getsize, mock_get_free_space, mock_transfer):
        self.device.file_copy("source_file", "dest_file")
        mock_transfer.assert_called_with(
            self.mock_native_ssh,
            source_file="source_file",
            dest_file="dest_file",
            file_system=FILE_SYSTEM,
            direction="put",
            overwrite_file=True,
        )

    @mock.patch("pyntc.devices.nxos_device.file_transfer")
    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024 * 1024 * 1024)
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024)
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, True])
    def test_file_copy_no_dest(self, mock_fcre, mock_getsize, mock_get_free_space, mock_transfer):
        self.device.file_copy("source_file")
        mock_transfer.assert_called_with(
            self.mock_native_ssh,
            source_file="source_file",
            dest_file="source_file",
            file_system=FILE_SYSTEM,
            direction="put",
            overwrite_file=True,
        )

    @mock.patch("pyntc.devices.nxos_device.file_transfer")
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[True])
    def test_file_copy_file_exists(self, mock_fcre, mock_transfer):
        self.device.file_copy("source_file", "dest_file")
        mock_transfer.assert_not_called()

    @mock.patch("pyntc.devices.nxos_device.file_transfer")
    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024 * 1024 * 1024)
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024)
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, False])
    def test_file_copy_fail(self, mock_fcre, mock_getsize, mock_get_free_space, mock_transfer):
        with self.assertRaises(FileTransferError):
            self.device.file_copy("source_file")
        mock_transfer.assert_called()

    @mock.patch("pyntc.devices.nxos_device.file_transfer", side_effect=OSError("scp broken"))
    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024 * 1024 * 1024)
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024)
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False])
    def test_file_copy_raises_on_transfer_error(self, mock_fcre, mock_getsize, mock_get_free_space, mock_transfer):
        with self.assertRaises(FileTransferError):
            self.device.file_copy("source_file")

    @mock.patch.object(NXOSDevice, "_get_free_space", return_value=1024)  # Only 1KB free
    @mock.patch("pyntc.devices.nxos_device.os.path.getsize", return_value=1024 * 1024)  # Trying to copy 1MB
    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False])
    def test_file_copy_raises_not_enough_free_space(self, mock_fcre, mock_getsize, mock_get_free_space):
        """Test file_copy raises NotEnoughFreeSpaceError when insufficient space."""
        with self.assertRaises(NotEnoughFreeSpaceError):
            self.device.file_copy("source_file")

    def test_reboot(self):
        self.device.reboot()
        self.mock_native_ssh.send_command.assert_any_call("terminal dont-ask")
        self.mock_native_ssh.send_command.assert_any_call("reload")

    def test_reboot_handles_read_timeout(self):
        from netmiko.exceptions import ReadTimeout as NetmikoReadTimeout

        self.mock_native_ssh.send_command.side_effect = [None, NetmikoReadTimeout("reload killed the session")]
        self.device.reboot()
        self.mock_native_ssh.send_command.assert_any_call("reload")

    def test_reboot_rejects_confirm_kwarg(self):
        with self.assertRaises(DeprecationWarning):
            self.device.reboot(confirm=True)

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
        expected = "!\nhostname n9k1\n!\n"
        self.mock_native_ssh.send_command.return_value = expected
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            self.device.backup_running_config(filename)

        self.mock_native_ssh.send_command.assert_called_with("show running-config")
        mock_file.assert_called_with(filename, "w", encoding="utf-8")
        mock_file().write.assert_called_with(expected)

    def test_rollback(self):
        self.mock_native_ssh.send_command.return_value = ""
        self.device.rollback("good_checkpoint")
        self.mock_native_ssh.send_command.assert_called_with("rollback running-config file good_checkpoint")

    def test_bad_rollback(self):
        self.mock_native_ssh.send_command.return_value = "Rollback failed: file bad_checkpoint does not exist"
        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpoint(self):
        self.mock_native_ssh.send_command.return_value = ""
        self.device.checkpoint("good_checkpoint")
        self.mock_native_ssh.send_command.assert_called_with("checkpoint file good_checkpoint")

    def test_checkpoint_failure(self):
        self.mock_native_ssh.send_command.return_value = "ERROR: Checkpoint named good_checkpoint already exists"
        with self.assertRaises(CommandError):
            self.device.checkpoint("good_checkpoint")

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

    def test_running_config(self):
        expected = "!\nhostname n9k1\n!\n"
        self.mock_native_ssh.send_command.return_value = expected
        result = self.device.running_config
        self.assertEqual(result, expected)
        self.mock_native_ssh.send_command.assert_called_with("show running-config")

    def test_set_timeout(self):
        self.device.set_timeout(120)
        self.assertEqual(self.device.timeout, 120)
        self.assertEqual(self.mock_native_ssh.timeout, 120)

    def test_starting_config(self):
        expected = self.device.show("show startup-config", raw_text=True)
        self.assertEqual(self.device.startup_config, expected)

    def test_refresh(self):
        self.assertTrue(hasattr(self.device.native, "_facts"))
        self.device.refresh()
        self.assertIsNone(self.device._uptime)
        self.assertFalse(hasattr(self.device.native, "_facts"))

    def test_refresh_clears_redundancy_state(self):
        self.mock_native_ssh.send_command.return_value = "Redundancy state = active"
        self.device.redundancy_state  # noqa: B018  # populate cache
        self.assertEqual(self.device._redundancy_state, "active")
        self.device.refresh()
        self.assertIsNone(self.device._redundancy_state)

    def test_redundancy_state_active(self):
        self.mock_native_ssh.send_command.return_value = "Redundancy state = active"
        self.assertEqual(self.device.redundancy_state, "active")
        self.mock_native_ssh.send_command.assert_called_with("show redundancy state")

    def test_redundancy_state_standby(self):
        self.mock_native_ssh.send_command.return_value = "Redundancy state = standby"
        self.assertEqual(self.device.redundancy_state, "standby")

    def test_redundancy_state_no_match_falls_back_to_active(self):
        self.mock_native_ssh.send_command.return_value = "% Invalid command at marker"
        self.assertEqual(self.device.redundancy_state, "active")

    def test_redundancy_state_session_error_falls_back_to_active(self):
        from netmiko.exceptions import NetmikoBaseException

        self.mock_native_ssh.send_command.side_effect = NetmikoBaseException("session dropped")
        self.assertEqual(self.device.redundancy_state, "active")

    def test_redundancy_state_is_memoized(self):
        self.mock_native_ssh.send_command.return_value = "Redundancy state = active"
        self.device.redundancy_state  # noqa: B018  # trigger memoization
        self.device.redundancy_state  # noqa: B018  # second access should not re-send
        self.assertEqual(self.mock_native_ssh.send_command.call_count, 1)

    def test_is_active_returns_true_when_active(self):
        self.mock_native_ssh.send_command.return_value = "Redundancy state = active"
        self.assertTrue(self.device.is_active())

    def test_is_active_returns_false_when_standby(self):
        self.mock_native_ssh.send_command.return_value = "Redundancy state = standby"
        self.assertFalse(self.device.is_active())

    @mock.patch.object(NXOSDevice, "show", return_value="bootflash:")
    def test_get_file_system(self, mock_show):
        self.assertEqual(self.device._get_file_system(), "bootflash:")
        mock_show.assert_called_with("dir", raw_text=True)

    @mock.patch.object(NXOSDevice, "show", return_value="no filesystems here")
    def test_get_file_system_not_found(self, mock_show):
        with self.assertRaises(FileSystemNotFoundError):
            self.device._get_file_system()
        mock_show.assert_called_with("dir", raw_text=True)

    @mock.patch.object(NXOSDevice, "show")
    def test_get_free_space(self, mock_show):
        """Test _get_free_space parses NXOS dir output correctly."""
        # NXOS dir output format with free space at the end
        mock_show.return_value = """Directory of bootflash:/
4096         Mar 03 22:47:15 2026  .rpmstore/
4733329408   bytes used
47171194880  bytes free
51904524288  bytes total

"""
        result = self.device._get_free_space()
        self.assertEqual(result, 47171194880)
        mock_show.assert_called_with("dir bootflash:", raw_text=True)

    @mock.patch.object(NXOSDevice, "show")
    def test_get_free_space_with_custom_filesystem(self, mock_show):
        """Test _get_free_space uses custom file system when provided."""
        mock_show.return_value = """Directory of disk0:/
1000000      bytes used
2000000      bytes free
3000000      bytes total

"""
        result = self.device._get_free_space("disk0:")
        self.assertEqual(result, 2000000)
        mock_show.assert_called_with("dir disk0:", raw_text=True)

    @mock.patch.object(NXOSDevice, "show")
    def test_get_free_space_raises_on_parse_error(self, mock_show):
        """Test _get_free_space raises CommandError when output can't be parsed."""
        mock_show.return_value = "Directory of bootflash:/\nNo free space info here\n"
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
        self.device.native_ssh.send_command.return_value = "Copy complete"
        with mock.patch.object(NXOSDevice, "verify_file", side_effect=[False, True]):
            self.device.remote_file_copy(src, file_system="bootflash:")
        self.device.native_ssh.send_command.assert_called_once()

    def test_remote_file_copy_transfer_fails_verification(self):
        src = FileCopyModel(
            download_url="http://example.com/nxos.bin",
            checksum="abc123",
            file_name="nxos.bin",
            hashing_algorithm="md5",
            timeout=30,
        )
        self.device.native_ssh.find_prompt.return_value = "host#"
        self.device.native_ssh.send_command.return_value = "Copy complete"
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


class TestNXOSDeviceDeprecationWarnings(unittest.TestCase):
    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_no_warning_on_default_kwargs(self, _mock_native, _mock_connect_handler):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            NXOSDevice("host", "user", "pass")
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(deprecation_warnings, [])

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_warning_on_non_default_transport(self, _mock_native, _mock_connect_handler):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            NXOSDevice("host", "user", "pass", transport="https")
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(len(deprecation_warnings), 1)
        self.assertIn("transport", str(deprecation_warnings[0].message))

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_warning_on_non_default_port(self, _mock_native, _mock_connect_handler):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            NXOSDevice("host", "user", "pass", port=8443)
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(len(deprecation_warnings), 1)
        self.assertIn("port", str(deprecation_warnings[0].message))

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_warning_on_non_default_verify(self, _mock_native, _mock_connect_handler):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            NXOSDevice("host", "user", "pass", verify=False)
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(len(deprecation_warnings), 1)
        self.assertIn("verify", str(deprecation_warnings[0].message))

    @mock.patch("pyntc.devices.nxos_device.ConnectHandler", create=True)
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    def test_warning_lists_multiple_kwargs(self, _mock_native, _mock_connect_handler):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            NXOSDevice("host", "user", "pass", transport="https", port=8443, verify=False)
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(len(deprecation_warnings), 1)
        message = str(deprecation_warnings[0].message)
        for kwarg in ("transport", "port", "verify"):
            self.assertIn(kwarg, message)


if __name__ == "__main__":
    unittest.main()
