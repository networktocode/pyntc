import unittest
import mock

from .device_mocks.asa import send_command, send_command_expect
from pyntc.devices.base_device import RollbackError
from pyntc.devices import ASADevice
from pyntc.devices.ios_device import FileTransferError
from pyntc.errors import CommandError, CommandListError, NTCFileNotFoundError


class TestASADevice(unittest.TestCase):
    @mock.patch.object(ASADevice, "open")
    @mock.patch.object(ASADevice, "close")
    @mock.patch("netmiko.cisco.cisco_asa_ssh.CiscoAsaSSH", autospec=True)
    def setUp(self, mock_miko, mock_close, mock_open):
        self.device = ASADevice("host", "user", "pass")

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

    def test_config(self):
        command = "interface gigabitethernet 0/0"

        result = self.device.config(command)
        assert result is None

        self.device.native.send_command_timing.assert_called_with(command)

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

    def test_facts(self):

        obj = self.device.facts

        assert obj is not None

    def test_count_setup(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_setup == 1

    def test_count_teardown(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_teardown == 0
