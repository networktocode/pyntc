from unittest import mock

# from .device_mocks.f5 import send_command, send_command_expect
from pyntc.devices.f5_device import F5Device
from pyntc.devices.f5_device import FileTransferError
from pyntc.errors import NTCFileNotFoundError

import pytest


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
    @mock.patch("bigsuds.BIGIP")
    @mock.patch("pyntc.devices.f5_device.ManagementRoot")
    def setup(self, api, big_ip):

        self.device = F5Device("host", "user", "password")
        self.device.native = big_ip

        if not getattr(self, "count_setup", None):
            self.count_setup = 0

        if not getattr(self, "count_teardown", None):
            self.count_teardown = 0

        # api.send_command_timing.side_effect = send_command
        # api.send_command_expect.side_effect = send_command_expect
        self.count_setup += 1

    def teardown(self):
        self.device.native.reset_mock()
        self.count_teardown += 1

    def test_file_copy_remote_exists(self):
        # Pull ManagementRoot mock instance off device
        api = self.device.api_handler
        # Patching out the _image_exists API call internal
        api.tm.util.unix_ls.exec_cmd.return_value.commandResult = "source_file"
        # Patching out the _file_copy_remote_md5 API call internal
        api.tm.util.bash.exec_cmd.return_value.commandResult = "dd7192cc7ed95bde7ecd06202312f3fe"

        name = "./test/unit/test_devices/device_mocks/f5/send_command/source_file"
        self.device.file_copy_remote_exists(name, "/shared/images/dest_file")

        api.tm.util.unix_ls.exec_cmd.assert_called_with("run", utilCmdArgs="/shared/images")
        api.tm.util.bash.exec_cmd.assert_called_with("run", utilCmdArgs='-c "md5sum /shared/images/source_file"')

    @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, True])
    @mock.patch("requests.post")
    def test_file_copy(self, mock_post, mock_fcre):
        # Pull ManagementRoot mock instance off device
        api = self.device.api_handler
        # Patching out the __get_free_space API call internal
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'

        name = "./test/unit/test_devices/device_mocks/f5/send_command/source_file"
        self.device.file_copy(name, "/shared/images/dest_file")

        # Check if _check_free_space worked
        api.tm.util.bash.exec_cmd.assert_called_with("run", utilCmdArgs='-c "vgdisplay -s --units G"')
        # Check if _upload_image REST API request worked
        URI = "https://host/mgmt/cm/autodeploy/software-image-uploads/source_file"
        data = b"Space, the final fronteer..."
        headers = {"Content-Type": "application/octet-stream", "Content-Range": "0-27/28"}
        mock_post.assert_called_with(URI, auth=("user", "password"), data=data, headers=headers, verify=False)

    @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, True])
    @mock.patch("requests.post")
    def test_file_copy_no_dest(self, mock_post, mock_fcre):
        api = self.device.api_handler
        api.tm.util.bash.exec_cmd.return_value.commandResult = '"vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]'

        name = "./test/unit/test_devices/device_mocks/f5/send_command/source_file"
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

        name = "./test/unit/test_devices/device_mocks/f5/send_command/source_file"
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

        name = "./test/unit/test_devices/device_mocks/f5/send_command/source_file"
        # Check if file transfer failed
        with pytest.raises(FileTransferError):
            self.device.file_copy(name, "/shared/images/source_file")

    def test_reboot(self):
        api = self.device.api_handler
        # vol1 = Volume("HD1.1", True)
        # vol2 = Volume("HD1.2", False)
        # Patch the _get_volumes return value, returns a list of volumes
        # api.tm.sys.software.volumes.get_collection.return_value.name = "HD1.1"
        # api.tm.sys.software.volumes.get_collection.return_value.active = True
        # api.tm.sys.software.volumes.get_collection.return_value.volumes = [vol1, vol2]

        volume = VOLUME
        # skip the wait_for_device_reboot
        with (mock.patch.object(self.device, "_wait_for_device_reboot", return_value=True)):
            self.device.reboot(confirm=True, volume=volume)
            # self.device.reboot(confirm=True)

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
            self.device.reboot(confirm=True, volume=volume)

        # # Check if _get_active_volume worked
        api.tm.sys.software.volumes.get_collection.assert_called()
        # Check if _reboot_to_volume worked
        api.tm.sys.software.volumes.exec_cmd.assert_called_with("reboot", volume=volume)

    def test_reboot_no_confirm(self):
        api = self.device.api_handler
        volume = VOLUME

        self.device.reboot(confirm=False, volume=volume)

        assert not api.tm.sys.software.volumes.exec_cmd.called

    def test_reboot_no_volume(self):
        api = self.device.api_handler

        with (mock.patch.object(self.device, "_wait_for_device_reboot", return_value=True)):
            self.device.reboot(confirm=True)

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
        # vol2 = Volume("HD1.2", False)
        # Patch the _get_volumes return value, returns a list of volumes
        # api.tm.sys.software.volumes.get_collection.return_value.name = "HD1.1"
        # api.tm.sys.software.volumes.get_collection.return_value.active = True
        api.tm.sys.software.images.get_collection.return_value = [im1]
        api.tm.sys.software.volumes.get_collection.return_value = [vol1]

        # import pdb

        # pdb.set_trace()
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
