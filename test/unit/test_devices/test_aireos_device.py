import pytest
from unittest import mock

from pyntc.devices import AIREOSDevice
from .device_mocks.aireos import send_command, send_command_expect
from pyntc.errors import CommandError


class TestAIREOSDevice:
    @mock.patch("pyntc.devices.aireos_device.ConnectHandler")
    def setup(self, api):

        if not getattr(self, "device", None):
            self.device = AIREOSDevice("host", "user", "password")

        self.device.native = api
        if not getattr(self, "count_setup", None):
            self.count_setup = 0

        if not getattr(self, "count_teardown", None):
            self.count_teardown = 0

        self.device = AIREOSDevice("host", "user", "password")
        api.send_command_timing.side_effect = send_command
        api.send_command_expect.side_effect = send_command_expect
        self.device.native = api
        self.count_setup += 1

    def teardown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()
        self.count_teardown += 1

    def test_send_command_private(self):
        self.device._send_command("test_send_command_private")
        self.device.native.send_command_timing.assert_called()
        self.device.native.send_command_timing.assert_called_with("test_send_command_private")

    def test_send_command_private_expect(self):
        self.device._send_command("test_send_command_private_expect", True, "Continue?")
        self.device.native.send_command_expect.assert_called()
        self.device.native.send_command_expect.assert_called_with("test_send_command_private_expect", expect_string="Continue?")

    def test_send_command_private_error(self):
        with pytest.raises(CommandError):
            self.device._send_command("test_send_command_private_error")
        self.device.native.send_command_timing.assert_called()



    def test_count_setup(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_setup == 1

    def test_count_teardown(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_teardown == 0
