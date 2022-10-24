import unittest
import mock

from pynxos.errors import CLIError

from .device_mocks.nxos import show, show_list
from pyntc.devices.nxos_device import NXOSDevice
from pyntc.devices.base_device import RollbackError, RebootTimerError
from pyntc.errors import CommandError, CommandListError, FileTransferError, NTCFileNotFoundError


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
    @mock.patch("pyntc.devices.nxos_device.NXOSNative", autospec=True)
    @mock.patch("pynxos.device.Device.facts", new_callable=mock.PropertyMock)
    def setUp(self, mock_device, mock_facts):
        self.device = NXOSDevice("host", "user", "pass")
        mock_device.show.side_effect = show
        mock_device.show_list.side_effect = show_list
        mock_facts.return_value = DEVICE_FACTS

        self.device.native = mock_device
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
        result = self.device.config_list(commands)

        self.assertIsNone(result)
        self.device.native.config_list.assert_called_with(commands)

    def test_bad_config_list(self):
        commands = ["interface Eth1", "apons"]
        self.device.native.config_list.side_effect = CLIError(commands[1], "Invalid command.")

        with self.assertRaisesRegex(CommandListError, commands[1]):
            self.device.config_list(commands)

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

        result = self.device.show_list(commands)
        self.assertIsInstance(result, list)

        self.assertIn("hostname", result[0])
        self.assertIn("simple_time", result[1])

        self.device.native.show_list.assert_called_with(commands, raw_text=False)

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        with self.assertRaisesRegex(CommandListError, "show badcommand"):
            self.device.show_list(commands)

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

    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, True])
    def test_file_copy(self, mock_fcre):
        self.device.file_copy("source_file", "dest_file")
        self.device.native.file_copy.assert_called_with("source_file", "dest_file", file_system=FILE_SYSTEM)
        self.device.native.file_copy.assert_called()

    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, True])
    def test_file_copy_no_dest(self, mock_fcre):
        self.device.file_copy("source_file")
        self.device.native.file_copy.assert_called_with("source_file", "source_file", file_system=FILE_SYSTEM)
        self.device.native.file_copy.assert_called()

    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[True])
    def test_file_copy_file_exists(self, mock_fcre):
        self.device.file_copy("source_file", "dest_file")
        self.device.native.file_copy.assert_not_called()

    @mock.patch.object(NXOSDevice, "file_copy_remote_exists", side_effect=[False, False])
    def test_file_copy_fail(self, mock_fcre):
        with self.assertRaises(FileTransferError):
            self.device.file_copy("source_file")
        self.device.native.file_copy.assert_called()

    def test_reboot(self):
        self.device.reboot()
        self.device.native.reboot.assert_called_with(confirm=True)

    def test_reboot_with_timer(self):
        with self.assertRaises(RebootTimerError):
            self.device.reboot(timer=3)

    def test_boot_options(self):
        expected = {"sys": "my_sys", "boot": "my_boot"}
        self.device.native.get_boot_options.return_value = expected
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, expected)

    def test_set_boot_options(self):
        self.device.set_boot_options(BOOT_IMAGE)
        self.device.native.set_boot_options.assert_called_with(f"{FILE_SYSTEM}{BOOT_IMAGE}", kickstart=None)

    def test_set_boot_options_dir(self):
        self.device.set_boot_options(BOOT_IMAGE, file_system=FILE_SYSTEM)
        self.device.native.set_boot_options.assert_called_with(f"{FILE_SYSTEM}{BOOT_IMAGE}", kickstart=None)

    def test_set_boot_options_kickstart(self):
        self.device.set_boot_options(BOOT_IMAGE, kickstart=KICKSTART_IMAGE)
        self.device.native.set_boot_options.assert_called_with(
            f"{FILE_SYSTEM}{BOOT_IMAGE}", kickstart=f"{FILE_SYSTEM}{KICKSTART_IMAGE}"
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

    @mock.patch("pynxos.device.Device.running_config", new_callable=mock.PropertyMock)
    def test_running_config(self, mock_rc):
        type(self.device.native).running_config = mock_rc
        self.device.running_config()
        self.device.native.running_config.assert_called_with()

    def test_starting_config(self):
        expected = self.device.show("show startup-config", raw_text=True)
        self.assertEqual(self.device.startup_config, expected)


if __name__ == "__main__":
    unittest.main()
