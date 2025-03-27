import unittest

import mock
from pyntc.devices import ios_xr_device as ios_xr_module
from pyntc.devices import IOSXRDevice
from pyntc.errors import FileTransferError
from .device_mocks.ios_xr import send_command, send_command_expect
from pyntc.devices.base_device import RollbackError

# BOOT_IMAGE = "c3560-advipservicesk9-mz.122-44.SE.bin"
# BOOT_OPTIONS_PATH = "pyntc.devices.ios_xr_device.IOSXRDevice.boot_options"
DEVICE_FACTS = {
    "version": "7.5.2",
    "hostname": "rtr2811",
    "uptime": "2 weeks, 4 days, 18 hours, 59 minutes",
    "hardware": "2811",
    "inventory_data": [{"sn":"123"},],
}
RECENT_UPTIME_DEVICE_FACTS = {
    "version": "7.5.2",
    "hostname": "rtr2811",
    "uptime": "9 minutes",
    "hardware": "2811",
    "inventory_data": [{"sn":"123"},],
}
# SHOW_BOOT_VARIABLE = (
#     "Current Boot Variables:\n"
#     "BOOT variable = flash:/cat3k_caa-universalk9.16.11.03a.SPA.bin;\n\n"
#     "Boot Variables on next reload:\n"
#     f"BOOT variable = flash:/{BOOT_IMAGE};\n"
#     "Manual Boot = no\n"
#     "Enable Break = no\n"
#     "Boot Mode = DEVICE\n"
#     "iPXE Timeout = 0"
# )
# SHOW_BOOT_PATH_LIST = (
#     f"BOOT path-list      : {BOOT_IMAGE}\n"
#     "Config file         : flash:/config.text\n"
#     "Private Config file : flash:/private-config.text\n"
#     "Enable Break        : yes\n"
#     "Manual Boot         : no\n"
#     "Allow Dev Key         : yes\n"
#     "HELPER path-list    :  \n"
#     "Auto upgrade        : yes\n"
#     "Auto upgrade path   :  \n"
#     "Boot optimization   : disabled\n"
#     "NVRAM/Config file\n"
#     "      buffer size:   524288\n"
#     "Timeout for Config\n"
#     "          Download:    0 seconds\n"
#     "Config Download\n"
#     "      via DHCP:       disabled (next boot: disabled)"
# )


class TestIOSXRDevice(unittest.TestCase):
    @mock.patch.object(IOSXRDevice, "open")
    @mock.patch.object(IOSXRDevice, "close")
    @mock.patch("netmiko.cisco.cisco_xr.CiscoXrSSH", autospec=True)
    def setUp(self, mock_miko, mock_close, mock_open):
        self.device = IOSXRDevice("host", "user", "pass")

        mock_miko.send_command_timing.side_effect = send_command
        mock_miko.send_command_expect.side_effect = send_command_expect
        self.device.native = mock_miko

    def tearDown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()

    def test_port(self):
        self.assertEqual(self.device.port, 22)

    def test_bad_show(self):
        command = "show microsoft"
        self.device.native.send_command.return_value = "Error: Microsoft"
        with self.assertRaises(ios_xr_module.CommandError):
            self.device.show(command)

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        results = ["Error: badcommand", "14:31:57.089 PST Tue Feb 10 2008"]

        self.device.native.send_command.side_effect = results

        with self.assertRaisesRegex(ios_xr_module.CommandListError, "show badcommand"):
            self.device.show(commands)

    @mock.patch("pyntc.devices.ios_xr_device.file_transfer")
    def test_file_copy_remote_exists_bad_md5(self, mock_ft):
        mock_ft.return_value = {
            "file_exists": True,
            "file_transfered": False,
            "file_verified": False,
        }
        with self.assertRaises(FileTransferError):
            self.device.file_copy("source.txt", "dest.txt")

    @mock.patch("pyntc.devices.ios_xr_device.file_transfer")
    def test_file_copy_remote_exists(self, mock_ft):
        mock_ft.return_value = {
            "file_exists": True,
            "file_transfered": False,
            "file_verified": True,
        }
        with self.assertRaises(FileTransferError):
            self.device.file_copy("source.txt", "dest.txt", overwrite=False)

    @mock.patch("pyntc.devices.ios_xr_device.file_transfer")
    def test_file_copy_success(self,mock_ft):
        mock_ft.return_value = {
            "file_exists": False,
            "file_transfered": True,
            "file_verified": True,
        }
        self.device.file_copy("source.txt", "dest.txt")

    @mock.patch("pyntc.devices.ios_xr_device.file_transfer")
    def test_file_copy_success_file_exists(self,mock_ft):
        mock_ft.return_value = {
            "file_exists": True,
            "file_transfered": True,
            "file_verified": True,
        }
        self.device.file_copy("source.txt", "dest.txt", overwrite=True)

    @mock.patch("pyntc.devices.ios_xr_device.file_transfer")
    def test_file_copy_fail(self, mock_ft):
        mock_ft.return_value = {
            "file_exists": False,
            "file_transfered": False,
            "file_verified": True,
        }
        with self.assertRaises(FileTransferError):
            self.device.file_copy("source.txt", "dest.txt")

    def test_reboot(self):
        self.device.reboot()
        self.device.native.send_command_timing.assert_any_call("reload")

    def test_rollback(self):
        self.device.native.send_command.return_value = "Loading"
        self.device.rollback("good_checkpoint")
        self.device.native.send_command.assert_called_with("load disk0:/good_checkpoint")

    def test_bad_rollback(self):
        # TODO: change to what the protocol would return
        self.device.native.send_command.return_value = "failed: No such file or directory"
        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpoint(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.send_command_timing.assert_any_call("copy running-config disk0:/good_checkpoint")

    @mock.patch.object(IOSXRDevice, "_raw_version_data", autospec=True)
    def test_uptime(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        uptime = self.device.uptime
        assert uptime == 413940

    @mock.patch.object(IOSXRDevice, "_raw_version_data", autospec=True)
    def test_uptime_string(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        uptime_string = self.device.uptime_string
        assert uptime_string == "04:18:59:00"
        assert self.device._has_reload_happened_recently() is False

    @mock.patch.object(IOSXRDevice, "_raw_version_data", autospec=True)
    def test_uptime_nine_minutes_string(self, mock_raw_version_data):
        mock_raw_version_data.return_value = RECENT_UPTIME_DEVICE_FACTS
        uptime_string = self.device.uptime_string
        assert uptime_string == "00:00:09:00"
        assert self.device._has_reload_happened_recently() is True

    def test_vendor(self):
        vendor = self.device.vendor
        assert vendor == "cisco"

    @mock.patch.object(IOSXRDevice, "_raw_version_data", autospec=True)
    def test_os_version(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        os_version = self.device.os_version
        assert os_version == "7.5.2"

    @mock.patch.object(IOSXRDevice, "_interfaces_detailed_list", autospec=True)
    def test_interfaces(self, mock_get_intf_list):
        expected = [{"interface": "FastEthernet0/0"}, {"interface": "FastEthernet0/1"}]
        mock_get_intf_list.return_value = expected
        interfaces = self.device.interfaces
        assert interfaces == ["FastEthernet0/0", "FastEthernet0/1"]

    @mock.patch.object(IOSXRDevice, "show", autospec=True)
    def test_hostname(self, mock_show):
        mock_show.return_value = "\nhostname rtr2811\n"
        hostname = self.device.hostname
        assert hostname == "rtr2811"

    def test_fqdn(self):
        fqdn = self.device.fqdn
        assert fqdn == "N/A"

    @mock.patch.object(IOSXRDevice, "_raw_inventory_data", autospec=True)
    def test_serial_number(self, mock_raw_inventory_data):
        mock_raw_inventory_data.return_value = DEVICE_FACTS["inventory_data"]
        print(DEVICE_FACTS["inventory_data"])
        serial_number = self.device.serial_number
        assert serial_number == "123"

    @mock.patch.object(IOSXRDevice, "_raw_version_data", autospec=True)
    def test_model(self, mock_raw_version_data):
        mock_raw_version_data.return_value = DEVICE_FACTS
        model = self.device.model
        assert model == "2811"

    def test_running_config(self):
        expected = self.device.show("show running-config")
        self.assertEqual(self.device.running_config, expected)

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

    # @mock.patch.object(IOSXRDevice, "_image_booted", side_effect=[False, True])
    # @mock.patch.object(IOSXRDevice, "set_boot_options")
    # @mock.patch.object(IOSXRDevice, "reboot")
    # @mock.patch.object(IOSXRDevice, "_wait_for_device_reboot")
    # def test_install_os(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted):
    #     state = self.device.install_os(BOOT_IMAGE)
    #     mock_set_boot.assert_called()
    #     mock_reboot.assert_called()
    #     mock_wait.assert_called()
    #     self.assertEqual(state, True)

    # @mock.patch.object(IOSXRDevice, "_image_booted", side_effect=[True])
    # @mock.patch.object(IOSXRDevice, "set_boot_options")
    # @mock.patch.object(IOSXRDevice, "reboot")
    # @mock.patch.object(IOSXRDevice, "_wait_for_device_reboot")
    # def test_install_os_already_installed(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted):
    #     state = self.device.install_os(BOOT_IMAGE)
    #     mock_image_booted.assert_called_once()
    #     mock_set_boot.assert_not_called()
    #     mock_reboot.assert_not_called()
    #     mock_wait.assert_not_called()
    #     self.assertEqual(state, False)

    # @mock.patch.object(IOSXRDevice, "_image_booted", side_effect=[False, False])
    # @mock.patch.object(IOSXRDevice, "set_boot_options")
    # @mock.patch.object(IOSXRDevice, "reboot")
    # @mock.patch.object(IOSXRDevice, "_wait_for_device_reboot")
    # @mock.patch.object(IOSXRDevice, "_raw_version_data")
    # def test_install_os_error(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted, mock_raw_version_data):
    #     mock_raw_version_data.return_value = DEVICE_FACTS
    #     self.assertRaises(ios_xr_module.OSInstallError, self.device.install_os, BOOT_IMAGE)

    # @mock.patch.object(IOSXRDevice, "os_version", new_callable=mock.PropertyMock)
    # @mock.patch.object(IOSXRDevice, "_image_booted", side_effect=[False, True])
    # @mock.patch.object(IOSXRDevice, "set_boot_options")
    # @mock.patch.object(IOSXRDevice, "show")
    # @mock.patch.object(IOSXRDevice, "reboot")
    # @mock.patch.object(IOSXRDevice, "_wait_for_device_reboot")
    # @mock.patch.object(IOSXRDevice, "_raw_version_data")
    # def test_install_os_not_enough_space(
    #     self,
    #     mock_raw_version_data,
    #     mock_wait,
    #     mock_reboot,
    #     mock_show,
    #     mock_set_boot,
    #     mock_image_booted,
    #     mock_os_version,
    # ):
    #     mock_raw_version_data.return_value = DEVICE_FACTS
    #     mock_os_version.return_value = "17.4.3"
    #     mock_show.return_value = "FAILED: There is not enough free disk available to perform this operation on switch 1. At least 1276287 KB of free disk is required"
    #     self.assertRaises(ios_xr_module.OSInstallError, self.device.install_os, image_name=BOOT_IMAGE, install_mode=True)
    #     mock_wait.assert_not_called()
    #     mock_reboot.assert_not_called()


if __name__ == "__main__":
    unittest.main()


