import pytest
from unittest import mock

from pyntc.devices import AIREOSDevice
from .device_mocks.aireos import send_command, send_command_expect
from pyntc.devices.aireos_device import (
    CommandError, RebootTimeoutError, CommandListError, FileTransferError, OSInstallError
)


BOOT_IMAGE = "8.2.170"
BOOT_PATH = "pyntc.devices.aireos_device.AIREOSDevice.boot_options"


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

    def test_enter_config_private(self):
        self.device._enter_config()
        self.device.native.config_mode.assert_called()

    def test_image_booted_private_true(self):
        image_booted = self.device._image_booted(BOOT_IMAGE)
        assert image_booted is True

    @mock.patch.object(AIREOSDevice, "show")
    def test_image_booted_private_false(self, mock_show):
        mock_show.side_effect = ["Product Version.....8.2"]
        image_booted = self.device._image_booted(BOOT_IMAGE)
        assert image_booted is False

    def test_send_command_private(self):
        self.device._send_command("test_send_command_private")
        self.device.native.send_command_timing.assert_called()
        self.device.native.send_command_timing.assert_called_with("test_send_command_private")

    def test_send_command_private_expect(self):
        self.device._send_command("test_send_command_private_expect", True, "Continue?")
        self.device.native.send_command_expect.assert_called()
        self.device.native.send_command_expect.assert_called_with(
            "test_send_command_private_expect", expect_string="Continue?"
        )

    def test_send_command_private_error(self):
        with pytest.raises(CommandError):
            self.device._send_command("test_send_command_private_error")
        self.device.native.send_command_timing.assert_called()

    def test_uptime_components_private(self):
        days, hours, minutes = self.device._uptime_components()
        assert days == 3
        assert hours == 2
        assert minutes == 20

    @mock.patch.object(AIREOSDevice, "open")
    def test_wait_for_device_reboot_private(self, mock_open):
        mock_open.side_effect = [Exception, Exception, True]
        self.device._wait_for_device_reboot()
        mock_open.assert_has_calls([mock.call()] * 3)

    @mock.patch.object(AIREOSDevice, "open")
    def test_wait_for_device_reboot_private_error(self, mock_open):
        mock_open.side_effect = [Exception]
        with pytest.raises(RebootTimeoutError):
            self.device._wait_for_device_reboot(1)

    def test_boot_options(self):
        assert self.device.boot_options["sys"] == BOOT_IMAGE

    @mock.patch.object(AIREOSDevice, "_send_command")
    @mock.patch.object(AIREOSDevice, "_enter_config")
    def test_config(self, mock_enter, mock_config):
        self.device.config("interface hostname virtual wlc1.site.com")
        mock_enter.assert_called()
        self.device.native.exit_config_mode.assert_called()

    @mock.patch.object(AIREOSDevice, "_send_command")
    @mock.patch.object(AIREOSDevice, "_enter_config")
    def test_config_list(self, mock_enter, mock_config):
        configs = [
            "interface hostname virtual wlc1.site.com",
            "config interface vlan airway 20",
        ]
        self.device.config_list(configs)
        mock_enter.assert_called()
        self.device.native.exit_config_mode.assert_called()
        mock_config.assert_has_calls([mock.call(cmd) for cmd in configs])

    @mock.patch.object(AIREOSDevice, "_send_command")
    @mock.patch.object(AIREOSDevice, "_enter_config")
    def test_config_list_error(self, mock_enter, mock_config):
        configs = [
            "interface hostname virtual wlc1.site.com",
            "config interface vlan airway 20",
        ]
        mock_config.side_effect = CommandError("interface hostname virtual wlc1.site.com", "test")
        with pytest.raises(CommandListError):
            self.device.config_list(configs)

        mock_enter.assert_called()
        self.device.native.exit_config_mode.assert_called()
        mock_config.assert_called_once()

    def test_connected_getter(self):
        assert self.device.connected in {True, False}

    def test_connected_setter(self):
        self.device.connected = True
        assert self.device.connected is True
        self.device.connected = False
        assert self.device.connected is False

    def test_close(self):
        assert self.device.connected
        self.device.close()
        self.device.native.disconnect.assert_called_once()
        assert not self.device.connected

    def test_close_not_connected(self):
        self.device.connected = False
        assert not self.device.connected
        self.device.close()
        assert not self.device.connected
        self.device.native.disconnect.assert_not_called()

    def test_enable_from_disable(self):
        self.device.native.check_enable_mode.side_effect = [False]
        self.device.native.check_config_mode.side_effect = [False]
        self.device.enable()
        self.device.native.enable.assert_called()
        self.device.native.exit_config_mode.assert_not_called()

    def test_enable_from_enable(self):
        self.device.native.check_enable_mode.side_effect = [True]
        self.device.native.check_config_mode.side_effect = [False]
        self.device.enable()
        self.device.native.enable.assert_not_called()
        self.device.native.exit_config_mode.assert_not_called()

    def test_enable_from_config(self):
        self.device.native.check_enable_mode.side_effect = [True]
        self.device.native.check_config_mode.side_effect = [True]
        self.device.enable()
        self.device.native.enable.assert_not_called()
        self.device.native.exit_config_mode.assert_called()

    def test_file_copy(self):
        self.device.file_copy("user", "pass", "10.1.1.1", "local/os_file")
        self.device.native.send_command_timing.assert_has_calls([
            mock.call("transfer download datatype code"),
            mock.call("transfer download mode sftp"),
            mock.call("transfer download username user"),
            mock.call("transfer download password pass"),
            mock.call("transfer download serverip 10.1.1.1"),
            mock.call("transfer download path local/"),
            mock.call("transfer download filename os_file"),
        ])

    def test_file_copy_error(self):
        with pytest.raises(FileTransferError):
            self.device.file_copy("invalid", "pass", "10.1.1.1", "local/os_file")

    @mock.patch.object(AIREOSDevice, "set_boot_options")
    @mock.patch.object(AIREOSDevice, "reboot")
    @mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
    @mock.patch.object(AIREOSDevice, "_image_booted")
    def test_install_os(self, mock_ib, mock_wait, mock_reboot, mock_sbo):
        mock_ib.side_effect = [False, True]
        assert self.device.install_os(BOOT_IMAGE) is True
        mock_ib.assert_has_calls([mock.call(BOOT_IMAGE)] * 2)

    @mock.patch.object(AIREOSDevice, "_image_booted", return_value=True)
    def test_install_os_no_install(self, mock_ib):
        assert self.device.install_os(BOOT_IMAGE) is False
        mock_ib.assert_called_once()

    @mock.patch.object(AIREOSDevice, "set_boot_options")
    @mock.patch.object(AIREOSDevice, "reboot")
    @mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
    @mock.patch.object(AIREOSDevice, "_image_booted")
    def test_install_os_error(self, mock_ib, mock_wait, mock_reboot, mock_sbo):
        mock_ib.side_effect = [False, False]
        with pytest.raises(OSInstallError):
            self.device.install_os(BOOT_IMAGE)
        mock_ib.assert_has_calls([mock.call(BOOT_IMAGE)] * 2)

    @mock.patch("pyntc.devices.aireos_device.ConnectHandler")
    def test_open_prompt_found(self, mock_ch):
        self.device.connected = True
        self.device.native.find_prompt.side_effect = [True]
        self.device.open()
        self.device.native.find_prompt.assert_called()
        mock_ch.assert_not_called()
        assert self.device.connected is True

    @mock.patch("pyntc.devices.aireos_device.ConnectHandler")
    def test_open_prompt_not_found(self, mock_ch):
        self.device.connected = True
        self.device.native.find_prompt.side_effect = [Exception]
        self.device.open()
        mock_ch.assert_called()
        assert self.device.connected is True

    @mock.patch("pyntc.devices.aireos_device.ConnectHandler")
    def test_open_not_connected(self, mock_ch):
        self.device.connected = False
        self.device.open()
        self.device.native.find_prompt.assert_not_called()
        mock_ch.assert_called()
        assert self.device.connected is True

    @mock.patch("pyntc.devices.aireos_device.RebootSignal")
    @mock.patch.object(AIREOSDevice, "show")
    def test_reboot_confirm(self, mock_show, mock_reboot):
        self.device.reboot(confirm=True)
        mock_show.assert_called()

    @mock.patch("pyntc.devices.aireos_device.RebootSignal")
    def test_reboot_no_confirm(self, mock_reboot):
        self.device.reboot(confirm=False)
        mock_reboot.assert_not_called()

    @mock.patch("pyntc.devices.aireos_device.RebootSignal")
    def test_reboot_error(self, mock_reboot):
        with pytest.raises(CommandError):
            self.device.reboot(confirm=True, timer=30)
        mock_reboot.assert_not_called()

    def test_save(self):
        save = self.device.save()
        self.device.native.save_config.assert_called()
        assert save is True

    @mock.patch.object(AIREOSDevice, "config")
    def test_set_boot_options(self, mock_cfg):
        with mock.patch(BOOT_PATH, new_callable=mock.PropertyMock) as boot_options:
            boot_options.side_effect = [{"sys": "1"}, {"sys": BOOT_IMAGE}]
            self.device.set_boot_options(BOOT_IMAGE)
        mock_cfg.assert_called()

    @mock.patch.object(AIREOSDevice, "config")
    def test_set_boot_options_already_set(self, mock_cfg):
        with mock.patch(BOOT_PATH, new_callable=mock.PropertyMock) as boot_options:
            boot_options.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
        mock_cfg.assert_not_called()

    @mock.patch.object(AIREOSDevice, "config")
    def test_set_boot_options_error(self, mock_cfg):
        with mock.patch(BOOT_PATH, new_callable=mock.PropertyMock) as boot_options:
            with pytest.raises(CommandError) as ce:
                boot_options.return_value = {"sys": "1"}
                self.device.set_boot_options(BOOT_IMAGE)
                assert ce.command == f"boot {BOOT_IMAGE}"
        mock_cfg.assert_called()

    @mock.patch.object(AIREOSDevice, "enable")
    def test_show(self, mock_enable):  # command, expect=False, expect_string=""):
        data = self.device.show("test send command private")
        assert data.strip() == "This is only a test"
        mock_enable.assert_called()

    def test_show_expect(self):
        data = self.device.show("test send command private expect")
        assert data.strip() == "This is only a test\nContinue?"

    @mock.patch.object(AIREOSDevice, "enable")
    def test_show_list(self, mock_enable):
        data = self.device.show_list(["test send command private", "show boot"])
        clean_data = [result.strip() for result in data]
        assert clean_data == ["This is only a test", "Primary Boot Image.....8.2.170"]
        mock_enable.assert_called()

    @mock.patch.object(AIREOSDevice, "_uptime_components")
    def test_uptime(self, mock_uc):
        mock_uc.side_effect = [(3, 2, 20)]
        assert self.device.uptime == 267600

    @mock.patch.object(AIREOSDevice, "_uptime_components")
    def test_uptime_string(self, mock_uc):
        mock_uc.side_effect = [(3, 2, 20)]
        assert self.device.uptime_string == "03:02:20:00"

    def test_count_setup(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_setup == 1

    def test_count_teardown(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_teardown == 0
