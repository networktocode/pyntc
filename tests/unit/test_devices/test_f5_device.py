from unittest import mock

import pytest

# from .device_mocks.f5 import send_command, send_command_expect
from pyntc.devices.f5_device import F5Device, FileTransferError
from pyntc.errors import NTCFileNotFoundError

BOOT_IMAGE = "BIGIP-11.3.0.2806.0.iso"
VOLUME = "HD1.1"


class Volume:
    def __init__(self, name, active, version, basebuild, status):
        self.name = name
        self.active = active
        self.version = version
        self.basebuild = basebuild
        self.status = status


class Image:
    def __init__(self, fullPath, version, build):
        self.fullPath = fullPath
        self.version = version
        self.build = build


class TestF5Device:
    def setup(self):
        with mock.patch("pyntc.devices.f5_device.ManagementRoot") as big_ip:
            self.device = F5Device("host", "user", "password")
            self.device.api_handler = big_ip

            if not getattr(self, "count_setup", None):
                self.count_setup = 0

            if not getattr(self, "count_teardown", None):
                self.count_teardown = 0

            self.count_setup += 1

    def teardown(self):
        self.device.api_handler.reset_mock()
        self.count_teardown += 1

    # def test_file_copy_remote_exists(self):
    #     # Pull ManagementRoot mock instance off device
    #     print(self.device)
    #     api = self.device.api_handler
    #     # Patching out the _image_exists API call internal
    #     api.tm.util.unix_ls.exec_cmd.return_value.commandResult = "source_file"
    #     # Patching out the _file_copy_remote_md5 API call internal
    #     api.tm.util.bash.exec_cmd.return_value.commandResult = "dd7192cc7ed95bde7ecd06202312f3fe"

    #     name = "./tests/unit/test_devices/device_mocks/f5/send_command/source_file"
    #     self.device.file_copy_remote_exists(name, "/shared/images/dest_file")

    #     api.tm.util.unix_ls.exec_cmd.assert_called_with("run", utilCmdArgs="/shared/images")
    #     api.tm.util.bash.exec_cmd.assert_called_with("run", utilCmdArgs='-c "md5sum /shared/images/source_file"')

    # @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, True])
    # @mock.patch("requests.post")
    # def test_file_copy(self, mock_post, mock_fcre):
    #     # Pull ManagementRoot mock instance off device
    #     api = self.device.api_handler
    #     # Patching out the __get_free_space API call internal
    #     api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'

    #     name = "./tests/unit/test_devices/device_mocks/f5/send_command/source_file"
    #     self.device.file_copy(name, "/shared/images/dest_file")

    #     # Check if _check_free_space worked
    #     api.tm.util.bash.exec_cmd.assert_called_with("run", utilCmdArgs='-c "vgdisplay -s --units G"')
    #     # Check if _upload_image REST API request worked
    #     URI = "https://host/mgmt/cm/autodeploy/software-image-uploads/source_file"
    #     data = b"Space, the final fronteer..."
    #     headers = {"Content-Type": "application/octet-stream", "Content-Range": "0-27/28"}
    #     mock_post.assert_called_with(URI, auth=("user", "password"), data=data, headers=headers, verify=False)

    @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, True])
    @mock.patch("requests.post")
    def test_file_copy_no_dest(self, mock_post, mock_fcre):
        api = self.device.api_handler
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'

        name = "./tests/unit/test_devices/device_mocks/f5/send_command/source_file"
        # the only difference with file_copy is that here we are testing with same source and dest file
        self.device.file_copy(name, "/shared/images/source_file")

        # Check if _check_free_space worked
        api.tm.util.bash.exec_cmd.assert_called_with("run", utilCmdArgs='-c "vgdisplay -s --units G"')
        # Check if _upload_image REST API request worked
        URI = "https://host/mgmt/cm/autodeploy/software-image-uploads/source_file"
        data = b"Space, the final fronteer..."
        headers = {"Content-Type": "application/octet-stream", "Content-Range": "0-27/28"}
        mock_post.assert_called_with(URI, auth=("user", "password"), data=data, headers=headers, verify=False)

    @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[True])
    @mock.patch("requests.post")
    def test_file_copy_file_exists(self, mock_post, mock_fcre):
        api = self.device.api_handler
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'

        name = "./tests/unit/test_devices/device_mocks/f5/send_command/source_file"
        self.device.file_copy(name, "/shared/images/dest_file")

        # Check if _check_free_space has not been called since file exists
        api.tm.util.bash.exec_cmd.assert_not_called()
        # Check if _upload_image REST API request has not been called
        mock_post.assert_not_called()

    @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, False])
    @mock.patch("requests.post")
    def test_file_copy_fail(self, mock_post, mock_fcre):
        # Pull ManagementRoot mock instance off device
        api = self.device.api_handler
        # Patching out the __get_free_space API call internal
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'

        name = "./tests/unit/test_devices/device_mocks/f5/send_command/source_file"
        # Check if file transfer failed
        with pytest.raises(FileTransferError):
            self.device.file_copy(name, "/shared/images/source_file")

    def test_reboot(self):
        api = self.device.api_handler
        # vol1 = Volume("HD1.1", True)
        # vol2 = Volume("HD1.2", False)
        # Patch the _get_volumes return value, returns a list of volumes
        # api.tm.sys.software.volumes.get_collection.return_value = [vol1, vol2]

        volume = VOLUME
        # skip the wait_for_device_reboot
        with (mock.patch.object(self.device, "_wait_for_device_reboot", return_value=True)):
            self.device.reboot(volume=volume)

        # # Check if _get_active_volume worked
        api.tm.sys.software.volumes.get_collection.assert_called()
        # Check if _reboot_to_volume worked
        api.tm.sys.software.volumes.exec_cmd.assert_called_with("reboot", volume="HD1.1")

    def test_reboot_with_timer(self):
        api = self.device.api_handler
        volume = VOLUME
        api.tm.sys.software.volumes.volume.load.return_value.active = True

        # skipping timeout! It's too long!!
        with (mock.patch.object(self.device, "_wait_for_device_reboot", timeout=0)):
            self.device.reboot(volume=volume)

        # # Check if _get_active_volume worked
        api.tm.sys.software.volumes.get_collection.assert_called()
        # Check if _reboot_to_volume worked
        api.tm.sys.software.volumes.exec_cmd.assert_called_with("reboot", volume=volume)

    def test_reboot_no_volume(self):
        api = self.device.api_handler

        with (mock.patch.object(self.device, "_wait_for_device_reboot", return_value=True)):
            self.device.reboot()

        # Check if _reboot_to_volume worked
        api.tm.util.bash.exec_cmd.assert_called_with("run", utilCmdArgs='-c "reboot"')

    def test_set_boot_options(self):
        api = self.device.api_handler
        image_name = BOOT_IMAGE
        volume = VOLUME

        # Patching out the __get_free_space API call internal
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'
        # Patching out _image_exists
        api.tm.util.unix_ls.exec_cmd.return_value.commandResult = image_name
        # Patching out _volume_exists for _image_install
        api.tm.sys.software.volumes.volume.exists.return_value = True

        with (mock.patch.object(self.device, "_wait_for_image_installed", timeout=0, return_value=None)):
            self.device.set_boot_options(image_name=image_name, volume=volume)

        api.tm.util.bash.exec_cmd.assert_called()
        api.tm.util.unix_ls.exec_cmd.assert_called_with("run", utilCmdArgs="/shared/images")
        api.tm.sys.software.images.exec_cmd.assert_called_with("install", name=image_name, volume=volume, options=[])

    def test_set_boot_options_no_image(self):
        api = self.device.api_handler
        image_name = BOOT_IMAGE
        volume = VOLUME

        # Patching out the __get_free_space API call internal
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'
        # Patching out _image_exists
        api.tm.util.unix_ls.exec_cmd.return_value.commandResult = image_name
        # Patching out _volume_exists for _image_install
        api.tm.sys.software.volumes.volume.exists.return_value = False

        with (mock.patch.object(self.device, "_wait_for_image_installed", timeout=0, return_value=None)):
            self.device.set_boot_options(image_name=image_name, volume=volume)

        api.tm.util.bash.exec_cmd.assert_called()
        api.tm.util.unix_ls.exec_cmd.assert_called_with("run", utilCmdArgs="/shared/images")
        api.tm.sys.software.images.exec_cmd.assert_called_with(
            "install", name=image_name, volume=volume, options=[{"create-volume": True}]
        )

    def test_set_boot_options_bad_boot(self):
        api = self.device.api_handler
        image_name = BOOT_IMAGE
        volume = VOLUME

        # Patching out the __get_free_space API call internal
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'
        # Patching out _image_exists
        api.tm.util.unix_ls.exec_cmd.return_value.commandResult = image_name
        # Patching out _volume_exists for _image_install
        api.tm.sys.software.volumes.volume.exists.return_value = False

        with (mock.patch.object(self.device, "_wait_for_image_installed", timeout=0, return_value=None)):
            with pytest.raises(NTCFileNotFoundError):
                self.device.set_boot_options(image_name="bad_image", volume=volume)

        api.tm.util.bash.exec_cmd.assert_called()
        api.tm.util.unix_ls.exec_cmd.assert_called_with("run", utilCmdArgs="/shared/images")
        api.tm.sys.software.images.exec_cmd.assert_not_called()

    def test_image_installed(self):
        api = self.device.api_handler
        image_name = BOOT_IMAGE
        volume = VOLUME

        vol1 = Volume("HD1.1", True, "W503", "W503", "complete")
        im1 = Image(BOOT_IMAGE, "W503", "W503")
        api.tm.sys.software.images.get_collection.return_value = [im1]
        api.tm.sys.software.volumes.get_collection.return_value = [vol1]

        installed = self.device.image_installed(image_name=image_name, volume=volume)
        assert installed

    def test_install_os(self):
        api = self.device.api_handler
        image_name = BOOT_IMAGE
        volume = VOLUME

        # Patching out the __get_free_space API call internal
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'
        # Patching out _image_exists
        api.tm.util.unix_ls.exec_cmd.return_value.commandResult = image_name
        # Patching out _image_install
        api.tm.sys.software.volumes.volume.exists.return_value = True

        with (mock.patch.object(self.device, "_wait_for_image_installed", timeout=0, return_value=None)):
            self.device.install_os(image_name=image_name, volume=volume)

        api.tm.util.bash.exec_cmd.assert_called()
        api.tm.sys.software.images.exec_cmd.assert_called_with("install", name=image_name, volume=volume, options=[])

    def test_count_setup(self):
        assert self.count_setup == 1

    def test_count_teardown(self):
        assert self.count_teardown == 0

    @mock.patch.object(F5Device, "_get_uptime", autospec=True)
    def test_uptime(self, mock_get_uptime):
        mock_get_uptime.return_value = 123
        uptime = self.device.uptime
        assert uptime == 123

    @mock.patch.object(F5Device, "_get_uptime", autospec=True)
    def test_uptime_string(self, mock_get_uptime):
        mock_get_uptime.return_value = 123
        uptime_string = self.device.uptime_string
        assert uptime_string == "00:00:02:03"

    def test_vendor(self):
        vendor = self.device.vendor
        assert vendor == "f5"

    @mock.patch.object(F5Device, "_get_version", autospec=True)
    def test_os_version(self, mock_get_version):
        mock_get_version.return_value = "16.0.1"
        os_version = self.device.os_version
        assert os_version == "16.0.1"

    @mock.patch.object(F5Device, "_get_interfaces_list", autospec=True)
    def test_interfaces(self, mock_get_intf_list):
        expected = ["Ethernet1", "Ethernet2", "Ethernet3", "Management1"]
        mock_get_intf_list.return_value = expected
        interfaces = self.device.interfaces
        assert interfaces == expected

    @mock.patch.object(F5Device, "fqdn", new_callable=mock.PropertyMock)
    def test_hostname_not_initialized(self, mock_fqdn):
        self.device._hostname = None
        mock_fqdn.return_value = "f5-spine3.ntc.com"
        assert self.device.hostname == "f5-spine3"
        mock_fqdn.assert_called_once()

    @mock.patch.object(F5Device, "fqdn", new_callable=mock.PropertyMock)
    def test_hostname_already_initialized(self, mock_fqdn):
        self.device._hostname = "f5-spine3"
        assert self.device.hostname == "f5-spine3"
        mock_fqdn.assert_not_called()

    def test_fqdn_not_initialized(self):
        self.device._fqdn = None
        global_setttings_mock = mock.Mock()
        global_setttings_mock.hostname = "f5-spine3.ntc.com"
        self.device.api_handler.tm.sys.global_settings.load.return_value = global_setttings_mock
        assert self.device.fqdn == "f5-spine3.ntc.com"
        self.device.api_handler.tm.sys.global_settings.load.assert_called_once()

    def test_fqdn_already_initialized(self):
        self.device._fqdn = "f5-spine3.ntc.com"
        assert self.device.fqdn == "f5-spine3.ntc.com"
        self.device.api_handler.tm.sys.global_settings.load.assert_not_called()

    @mock.patch.object(F5Device, "_get_serial_number", autospec=True)
    def test_serial_number(self, mock_get_serial):
        mock_get_serial.return_value = ""
        serial_number = self.device.serial_number
        assert serial_number == ""

    @mock.patch.object(F5Device, "_get_model", autospec=True)
    def test_model(self, mock_get_model):
        mock_get_model.return_value = "vF5"
        model = self.device.model
        assert model == "vF5"

    @mock.patch.object(F5Device, "_get_vlans", autospec=True)
    def test_vlans(self, mock_vlan_list):
        mock_vlan_list.return_value = ["1", "2", "10"]
        expected = ["1", "2", "10"]
        vlans = self.device.vlans

        assert vlans == expected
