from unittest import mock

# from .device_mocks.f5 import send_command, send_command_expect
from pyntc.devices.f5_device import F5Device

# import requests


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
        # Pull ManagementRoot mock instance off device
        api = self.device.api_handler
        # Patching out the __get_free_space API call internal
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

    # @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[True])
    # def test_file_copy_file_exists(self, mock_fcre):
    #     self.device.native.file_copy("source_file", "dest_file")
    #     self.device.native.file_copy.assert_not_called()

    # @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, False])
    # def test_file_copy_fail(self, mock_fcre):
    #     with self.assertRaises(FileTransferError):
    #         self.device.file_copy("source_file")
    #     self.device.native.file_copy.assert_called()

    def test_count_setup(self):
        assert self.count_setup == 1

    def test_count_teardown(self):
        assert self.count_teardown == 0
