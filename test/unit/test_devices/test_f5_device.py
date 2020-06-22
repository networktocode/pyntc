from unittest import mock

# from .device_mocks.f5 import send_command, send_command_expect
from pyntc.devices.f5_device import F5Device


FILE_SYSTEM = "/shared/images"


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
        self.device.native.file_copy_remote_exists.return_value = False
        with mock.patch.object(F5Device, "_image_match", return_value=True):
            result = self.device.file_copy_remote_exists("source_file")
            assert result

    @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, True])
    @mock.patch.object(F5Device, "_check_free_space", return_value=7)
    @mock.patch.object(F5Device, "_upload_image", return_value="source_file")
    def test_file_copy(self, mock_fcre, mock_fs, mock_ui):
        self.device.file_copy("source_file")
        # self.device._upload_image.assert_called_with("source_file")
        self.device.native.file_copy.assert_called()

    # @mock.patch.object(F5Device, "file_copy_remote_exists", side_effect=[False, True])
    # def test_file_copy_no_dest(self, mock_fcre):
    #     self.device.file_copy("source_file")
    #     self.device.native.file_copy.assert_called_with("source_file", "source_file", file_system=FILE_SYSTEM)
    #     self.device.native.file_copy.assert_called()

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
