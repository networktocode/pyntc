import unittest
import mock
import os

from .device_mocks.ios import send_command, send_command_expect
from pyntc.devices.base_device import RollbackError
from pyntc.devices import IOSDevice
from pyntc.devices.ios_device import FileTransferError
from pyntc.errors import CommandError, CommandListError, NTCFileNotFoundError


BOOT_IMAGE = "c3560-advipservicesk9-mz.122-44.SE"
BOOT_OPTIONS_PATH = "pyntc.devices.ios_device.IOSDevice.boot_options"


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

    def test_config(self):
        command = "interface fastEthernet 0/1"
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.send_command_timing.assert_called_with(command)

    def test_bad_config(self):
        command = "asdf poknw"

        try:
            with self.assertRaisesRegex(CommandError, command):
                self.device.config(command)
        finally:
            self.device.native.reset_mock()

    def test_config_list(self):
        commands = ["interface fastEthernet 0/1", "no shutdown"]
        result = self.device.config_list(commands)

        self.assertIsNone(result)

        for cmd in commands:
            self.device.native.send_command_timing.assert_any_call(cmd)

    def test_bad_config_list(self):
        commands = ["interface fastEthernet 0/1", "apons"]
        results = ["ok", "Error: apons"]

        self.device.native.send_command_timing.side_effect = results

        with self.assertRaisesRegex(CommandListError, commands[1]):
            self.device.config_list(commands)

    def test_show(self):
        command = "show ip arp"
        result = self.device.show(command)

        self.assertIsInstance(result, str)
        self.assertIn("Protocol", result)
        self.assertIn("Address", result)

        self.device.native.send_command_timing.assert_called_with(command)

    def test_bad_show(self):
        command = "show microsoft"
        self.device.native.send_command_timing.return_value = "Error: Microsoft"
        with self.assertRaises(CommandError):
            self.device.show(command)

    def test_show_list(self):
        commands = ["show version", "show clock"]

        result = self.device.show_list(commands)
        self.assertIsInstance(result, list)

        self.assertIn("uptime is", result[0])
        self.assertIn("UTC", result[1])

        calls = list(mock.call(x) for x in commands)
        self.device.native.send_command_timing.assert_has_calls(calls)

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        results = ["Error: badcommand", "14:31:57.089 PST Tue Feb 10 2008"]

        self.device.native.send_command_timing.side_effect = results

        with self.assertRaisesRegex(CommandListError, "show badcommand"):
            self.device.show_list(commands)

    def test_save(self):
        result = self.device.save()
        self.assertTrue(result)
        self.device.native.send_command_timing.assert_any_call("copy running-config startup-config")

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertTrue(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_bad_md5(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = False

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_not(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(self.device.native, "path/to/source_file", "source_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_different_dest(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value

        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("source_file", "dest_file")

        mock_ft.assert_called_with(self.device.native, "source_file", "dest_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_fail(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = Exception
        mock_ft_instance.check_file_exists.return_value = False

        with self.assertRaises(FileTransferError):
            self.device.file_copy("source_file")

    def test_reboot(self):
        self.device.reboot(confirm=True)
        self.device.native.send_command_timing.assert_any_call("reload")

    def test_reboot_with_timer(self):
        self.device.reboot(confirm=True, timer=5)
        self.device.native.send_command_timing.assert_any_call("reload in 5")

    def test_reboot_no_confirm(self):
        self.device.reboot()
        assert not self.device.native.send_command_timing.called

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="bootflash:")
    def test_boot_options_show_bootvar(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = f"BOOT variable = bootflash:{BOOT_IMAGE}"
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command_timing.assert_called_with("show bootvar")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    def test_boot_options_show_boot(self, mock_boot):
        show_boot_out = (
            "Current Boot Variables:\n"
            "BOOT variable = flash:/cat3k_caa-universalk9.16.11.03a.SPA.bin;\n\n"
            "Boot Variables on next reload:\n"
            f"BOOT variable = flash:/{BOOT_IMAGE};\n"
            "Manual Boot = no\n"
            "Enable Break = no\n"
            "Boot Mode = DEVICE\n"
            "iPXE Timeout = 0"
        )
        results = [CommandError("show bootvar", "fail"), show_boot_out]
        self.device.native.send_command_timing.side_effect = results
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command_timing.assert_called_with("show boot")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="bootflash:")
    def test_boot_options_show_run(self, mock_boot):
        results = [
            CommandError("show bootvar", "fail"),
            CommandError("show bootvar", "fail"),
            f"boot system flash bootflash:/{BOOT_IMAGE}",
            "Directory of bootflash:/",
        ]
        self.device.native.send_command_timing.side_effect = results
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command_timing.assert_called_with("show run | inc boot")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    @mock.patch.object(IOSDevice, "config_list", return_value=None)
    def test_set_boot_options(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
            mock_cl.assert_called_with(["no boot system", f"boot system flash:/{BOOT_IMAGE}"])

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    @mock.patch.object(IOSDevice, "config_list", side_effect=[CommandError("boot system", "fail"), None])
    def test_set_boot_options_with_spaces(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
            mock_cl.assert_called_with(["no boot system", f"boot system flash {BOOT_IMAGE}"])

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    def test_set_boot_options_no_file(self, mock_fs):
        with self.assertRaises(NTCFileNotFoundError):
            self.device.set_boot_options("bad_image.bin")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    @mock.patch.object(IOSDevice, "boot_options", return_value={"sys": "bad_image.bin"})
    @mock.patch.object(IOSDevice, "config_list", return_value=None)
    def test_set_boot_options_bad_boot(self, mock_cl, mock_bo, mock_fs):
        with self.assertRaises(CommandError):
            self.device.set_boot_options(BOOT_IMAGE)
            mock_bo.assert_called_once()

    def test_backup_running_config(self):
        filename = "local_running_config"
        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        self.assertEqual(contents, self.device.running_config)
        os.remove(filename)

    def test_rollback(self):
        self.device.rollback("good_checkpoint")
        self.device.native.send_command_timing.assert_called_with("configure replace flash:good_checkpoint force")

    def test_bad_rollback(self):
        # TODO: change to what the protocol would return
        self.device.native.send_command_timing.return_value = "Error: rollback unsuccessful"
        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpoint(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.send_command_timing.assert_any_call("copy running-config good_checkpoint")

    def test_facts(self):
        expected = {
            "uptime": 413940,
            "vendor": "cisco",
            "uptime_string": "04:18:59:00",
            "interfaces": ["FastEthernet0/0", "FastEthernet0/1"],
            "hostname": "rtr2811",
            "fqdn": "N/A",
            "os_version": "15.1(3)T4",
            "serial_number": "",
            "model": "2811",
            "vlans": [],
            "cisco_ios_ssh": {"config_register": "0x2102"},
        }
        facts = self.device.facts
        self.assertEqual(facts, expected)

        self.device.native.send_command_timing.reset_mock()
        facts = self.device.facts
        self.assertEqual(facts, expected)

        self.device.native.send_command_timing.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
