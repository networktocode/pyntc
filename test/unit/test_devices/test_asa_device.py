import unittest
import mock

from .device_mocks.ios import send_command, send_command_expect
from pyntc.devices import ASADevice


BOOT_IMAGE = "asa9-12-3-12-smp-k8.bin"


class TestASADevice(unittest.TestCase):
    @mock.patch.object(ASADevice, "open")
    @mock.patch.object(ASADevice, "close")
    @mock.patch("netmiko.cisco.cisco_ios.CiscoIosSSH", autospec=True)
    def setUp(self, mock_miko, mock_close, mock_open):
        self.device = ASADevice("host", "user", "pass")

        mock_miko.send_command_timing.side_effect = send_command
        mock_miko.send_command_expect.side_effect = send_command_expect
        self.device.native = mock_miko

    def tearDown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_boot_options_dir(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = f"Current BOOT variable = disk0:/{BOOT_IMAGE}"
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command_timing.assert_called_with("show boot | i BOOT variable")

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_boot_options_none(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = ""
        boot_options = self.device.boot_options
        self.assertIs(boot_options["sys"], None)

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
