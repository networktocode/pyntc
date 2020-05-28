import unittest
import mock
import os

from .device_mocks.ios import send_command, send_command_expect
from pyntc.devices.base_device import RollbackError
from pyntc.devices import IOSDevice
from pyntc.devices.ios_device import FileTransferError
from pyntc.errors import CommandError, CommandListError, NTCFileNotFoundError


class TestASADevice(unittest.TestCase):
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
