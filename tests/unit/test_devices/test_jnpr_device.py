import os
import unittest
from tempfile import NamedTemporaryFile

import mock
import pytest
from jnpr.junos.exception import ConfigLoadError

from pyntc.devices import JunosDevice
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    FileTransferError,
    NotEnoughFreeSpaceError,
    OSInstallError,
    RebootTimeoutError,
)
from pyntc.utils.models import FileCopyModel

# Shared fake storage_usage() return value so tests exercising file_copy and
# remote_file_copy do not trip the new pre-transfer free-space probe. "10G"
# on /var/tmp is plenty of room for the tiny temp files and fake file sizes
# these tests use.
STORAGE_USAGE_PLENTY = {
    "/dev/ad0s1f": {
        "mount": "/var/tmp",
        "total": "10G",
        "total_blocks": 20971520,
        "used": "0B",
        "used_blocks": 0,
        "used_pct": "0%",
        "avail": "10G",
        "avail_block": 20971520,
    },
}

DEVICE_FACTS = {
    "domain": "ntc.com",
    "hostname": "vmx3",
    "ifd_style": "CLASSIC",
    "version_RE0": "15.1F4.15",
    "2RE": False,
    "serialnumber": "VMX9a",
    "fqdn": "vmx3.ntc.com",
    "virtual": True,
    "switch_style": "BRIDGE_DOMAIN",
    "version": "15.1F4.15",
    "master": "RE0",
    "HOME": "/var/home/ntc",
    "model": "VMX",
    "RE0": {
        "status": "OK",
        "last_reboot_reason": "0x200:normal shutdown ",
        "model": "RE-VMX",
        "up_time": "7 minutes, 35 seconds",
        "mastership_state": "master",
    },
    "vc_capable": False,
    "personality": "MX",
}


class TestJnprDevice(unittest.TestCase):
    def setUp(self):
        self.mock_sw = mock.patch("pyntc.devices.jnpr_device.JunosNativeSW", autospec=True)
        self.mock_fs = mock.patch("pyntc.devices.jnpr_device.JunosNativeFS", autospec=True)
        self.mock_config = mock.patch("pyntc.devices.jnpr_device.JunosNativeConfig", autospec=True)
        self.mock_device = mock.patch("pyntc.devices.jnpr_device.JunosNativeDevice", autospec=True)

        self.mock_sw.start()
        self.mock_fs.start()
        self.mock_config.start()
        self.mock_device.start()

        self.device = JunosDevice("host", "user", "pass")
        self.device.native.facts = DEVICE_FACTS

    def tearDown(self):
        self.mock_sw.stop()
        self.mock_fs.stop()
        self.mock_config.stop()
        self.mock_device.stop()

    def test_config_pass_string(self):
        command = "set interfaces lo0"
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.cu.load.assert_called_with(command, format_type="set")
        self.device.cu.commit.assert_called_with()

    def test_config_pass_list(self):
        commands = ["set interfaces lo0", "set snmp community jason"]
        result = self.device.config(commands)

        self.assertIsNone(result)
        self.device.cu.load.assert_has_calls(mock.call(command, format_type="set") for command in commands)
        self.device.cu.commit.assert_called_with()

    @mock.patch.object(JunosDevice, "config")
    def test_config_list(self, mock_config):
        commands = ["set interfaces lo0", "set snmp community jason"]

        self.device.config(commands, format_type="set")
        self.device.config.assert_called_with(commands, format_type="set")

    def test_bad_config_pass_string(self):
        command = "asdf poknw"
        self.device.cu.load.side_effect = ConfigLoadError(command)

        with pytest.raises(CommandError) as err:
            self.device.config(command)
        assert err.value.command == command

    def test_bad_config_pass_list(self):
        commands = ["set interface lo0", "apons"]

        def load_side_effect(*args, **kwargs):
            if args[0] == commands[1]:
                raise ConfigLoadError(args[0])

        self.device.cu.load.side_effect = load_side_effect

        with pytest.raises(CommandListError) as err:
            self.device.config(commands)
        assert err.value.command == commands[1]

    def test_show_pass_string(self):
        command = "show configuration snmp"

        expected = """
            community public {
                authorization read-only;
            }
            community networktocode {
                authorization read-only;
            }
        """

        self.device.native.cli.return_value = expected
        result = self.device.show(command)

        self.assertEqual(result, expected)
        self.device.native.cli.assert_called_with(command, warning=False)

    def test_show_pass_list(self):
        commands = ["show vlans", "show snmp v3"]

        def cli_side_effect(*args, **kwargs):
            cli_command = args[0]
            if cli_command == commands[0]:
                return "a"
            if cli_command == commands[1]:
                return "b"

        self.device.native.cli.side_effect = cli_side_effect

        result = self.device.show(commands)
        self.assertIsInstance(result, list)

        self.assertEqual("a", result[0])
        self.assertEqual("b", result[1])

        self.device.native.cli.assert_any_call(commands[0], warning=False)
        self.device.native.cli.assert_any_call(commands[1], warning=False)

    def test_bad_show_non_show_pass_string(self):
        command = "configure something"
        response = 'Juniper "show" commands must begin with "show".'
        with pytest.raises(CommandError) as err:
            self.device.show(command)
        assert err.value.command == "configure something"
        assert err.value.cli_error_msg == response

    def test_bad_show_non_show_pass_list(self):
        commands = ["show version", "configure something"]
        response = [
            "valid",
            '\nCommand configure something failed with message: Juniper "show" commands must begin with "show".\nCommand List: \n\tshow version\n\tconfigure something\n',
        ]
        with pytest.raises(CommandListError) as err:
            self.device.show(commands)
        assert err.value.command == commands[1]
        assert err.value.message == response[1]

    @mock.patch.object(JunosDevice, "show")
    def test_show_list(self, mock_show):
        commands = ["show vlans", "show snmp v3"]

        self.device.show(commands)
        self.device.show.assert_called_with(commands)

    @mock.patch("pyntc.devices.jnpr_device.JunosDevice.startup_config", new_callable=mock.PropertyMock)
    @mock.patch("pyntc.devices.jnpr_device.SCP", autospec=True)
    def test_save(self, mock_scp, mock_startup_config):
        mock_startup_config.return_value = "file contents"

        result = self.device.save(filename="saved_config")

        self.assertTrue(result)
        mock_startup_config.assert_called_once_with()

    def test_file_copy_remote_exists(self):
        temp_file = NamedTemporaryFile(mode="w")
        temp_file.write("file contents")
        temp_file.flush()

        local_checksum = "4a8ec4fa5f01b4ab1a0ab8cbccb709f0"
        self.device.fs.checksum.return_value = local_checksum

        result = self.device.file_copy_remote_exists(temp_file.name, "dest")

        self.assertTrue(result)
        self.device.fs.checksum.assert_called_with(path="dest", calc="md5")

    def test_file_copy_remote_exists_failure(self):
        temp_file = NamedTemporaryFile(mode="w")
        temp_file.write("file contents")
        temp_file.flush()

        self.device.fs.checksum.return_value = "deadbeef"

        result = self.device.file_copy_remote_exists(temp_file.name, "dest")

        self.assertFalse(result)
        self.device.fs.checksum.assert_called_with(path="dest", calc="md5")

    @mock.patch("pyntc.devices.jnpr_device.SCP")
    def test_file_copy(self, mock_scp):
        temp_file = NamedTemporaryFile(mode="w")
        temp_file.write("file contents")
        temp_file.flush()

        local_checksum = "4a8ec4fa5f01b4ab1a0ab8cbccb709f0"
        self.device.fs.checksum.side_effect = ["", local_checksum]
        self.device.fs.storage_usage.return_value = STORAGE_USAGE_PLENTY
        self.device.file_copy(temp_file.name, "dest")
        mock_scp.assert_called_with(self.device.native)

    def test_reboot(self):
        self.device.reboot()
        self.device.sw.reboot.assert_called_with(in_min=0)

    @mock.patch("pyntc.devices.jnpr_device.time.sleep")
    def test_wait_for_device_to_reboot(self, mock_sleep):
        with mock.patch.object(self.device, "open") as mock_open:
            # Emulate the device disconnected and reconnecting
            type(self.device.native).connected = mock.PropertyMock(side_effect=[True, False, True])
            mock_open.side_effect = [Exception, Exception, True]
            self.device.reboot(wait_for_reload=True, timeout=3)
            mock_open.assert_has_calls([mock.call()] * 3)

    @mock.patch("pyntc.devices.jnpr_device.time.sleep")
    def test_wait_for_device_to_reboot_error(self, mock_sleep):
        with mock.patch.object(self.device, "open") as mock_open:
            type(self.device.native).connected = mock.PropertyMock(side_effect=[True, False])
            mock_open.side_effect = Exception
            with pytest.raises(RebootTimeoutError):
                self.device.reboot(wait_for_reload=True, timeout=1)

    @mock.patch("pyntc.devices.jnpr_device.JunosDevice.running_config", new_callable=mock.PropertyMock)
    def test_backup_running_config(self, mock_run):
        filename = "local_running_config"

        fake_contents = "fake contents"
        mock_run.return_value = fake_contents

        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        self.assertEqual(contents, fake_contents)
        os.remove(filename)

    @mock.patch("pyntc.devices.jnpr_device.SCP")
    def test_rollback(self, mock_scp):
        self.device.rollback("good_checkpoint")

        mock_scp.assert_called_with(self.device.native)
        assert self.device.cu.load.called
        assert self.device.cu.commit.called

    @mock.patch("pyntc.devices.jnpr_device.SCP", autospec=True)
    def test_checkpoint(self, mock_scp):
        self.device.show = mock.MagicMock()
        self.device.show.return_value = "file contents"
        self.device.checkpoint("saved_config")
        self.device.show.assert_called_with("show config")

    def test_uptime(self):
        uptime = self.device.uptime
        assert uptime == 455

    def test_uptime_string(self):
        uptime_string = self.device.uptime_string
        assert uptime_string == "00:00:07:35"

    def test_vendor(self):
        vendor = self.device.vendor
        assert vendor == "juniper"

    def test_os_version(self):
        os_version = self.device.os_version
        assert os_version == "15.1F4.15"

    def test_interfaces(self):
        self.device._get_interfaces = mock.MagicMock()
        self.device._get_interfaces.return_value = ["lo0", "ge0"]
        interfaces = self.device.interfaces
        assert interfaces == ["lo0", "ge0"]

    def test_hostname(self):
        hostname = self.device.hostname
        assert hostname == "vmx3"

    def test_fqdn(self):
        fqdn = self.device.fqdn
        assert fqdn == "vmx3.ntc.com"

    def test_serial_number(self):
        serial_number = self.device.serial_number
        assert serial_number == "VMX9a"

    def test_model(self):
        model = self.device.model
        assert model == "VMX"

    def test_running_config(self):
        self.device.show = mock.MagicMock()
        expected = "running config"
        self.device.show.return_value = expected

        result = self.device.running_config
        self.assertEqual(result, expected)

    def test_starting_config(self):
        self.device.show = mock.MagicMock()
        expected = "running config"
        self.device.show.return_value = expected

        result = self.device.startup_config
        self.assertEqual(result, expected)

    def test_file_copy_local_file_exists(self):
        with self.subTest("File does not exist"):
            result = self.device._file_copy_local_file_exists("/dev/null/foo")
            self.assertFalse(result)

        with self.subTest("File exists"):
            with NamedTemporaryFile() as fp:
                result = self.device._file_copy_local_file_exists(fp.name)
                self.assertTrue(result)

    def test_file_copy_local_md5(self):
        with self.subTest("File does not exist"):
            result = self.device._file_copy_local_md5("/dev/null/foo")
            self.assertIsNone(result)

        with self.subTest("File exists"):
            with NamedTemporaryFile() as fp:
                fp.write("file contents".encode())
                fp.flush()

                checksum = "4a8ec4fa5f01b4ab1a0ab8cbccb709f0"
                result = self.device._file_copy_local_md5(fp.name)
                self.assertEqual(result, checksum)

    def test_install_os(self):
        with mock.patch.object(self.device, "reboot") as mock_reboot:
            with self.subTest("sw.install returns a bool"):
                self.device.sw.install.return_value = True
                self.device.install_os(image_name="image.bin", checksum="c0ffee")
                mock_reboot.assert_called_once_with(wait_for_reload=True)

            with self.subTest("sw.install returns a tuple and fails"):
                self.device.sw.install.return_value = (False, "install failure")
                with self.assertRaises(OSInstallError):
                    self.device.install_os(image_name="image.bin", checksum="c0ffee")

    def test_check_file_exists(self):
        self.device.check_file_exists("foo.txt")
        self.device.fs.ls.assert_called_once_with("foo.txt")

    def test_compare_file_checksum(self):
        checksum = "c0ffee"
        with mock.patch.object(self.device, "get_remote_checksum") as mock_get_remote_checksum:
            with self.subTest("checksum matches"):
                mock_get_remote_checksum.return_value = checksum
                result = self.device.compare_file_checksum(checksum, "foo.txt", hashing_algorithm="sha1")
                mock_get_remote_checksum.assert_called_once_with("foo.txt", "sha1")
                self.assertTrue(result)
            with self.subTest("checksum does not match"):
                mock_get_remote_checksum.return_value = f"{checksum}ffff"
                mock_get_remote_checksum.reset_mock()
                result = self.device.compare_file_checksum(checksum, "foo.txt", hashing_algorithm="sha1")
                mock_get_remote_checksum.assert_called_once_with("foo.txt", "sha1")
                self.assertFalse(result)

    @mock.patch("pyntc.devices.jnpr_device.time.sleep")
    def test_remote_file_copy(self, mock_sleep):
        ftp_url = "ftp://example.com/file.bin"
        md5_checksum = "c0ffee"
        filename = "file.bin"
        dest_file = "/var/tmp/file.bin"
        src_file = FileCopyModel(
            download_url=ftp_url,
            checksum=md5_checksum,
            file_name=filename,
            hashing_algorithm="md5",
            timeout=1200,
            file_size=330656851,
        )

        self.device.fs.cp.return_value = True
        self.device.fs.storage_usage.return_value = STORAGE_USAGE_PLENTY

        with mock.patch.object(self.device, "verify_file") as mock_verify_file:
            with self.subTest("invalid src argument"):
                with self.assertRaises(TypeError):
                    self.device.remote_file_copy(ftp_url, dest=dest_file)

            with self.subTest("file already exists"):
                mock_verify_file.return_value = True
                result = self.device.remote_file_copy(src_file, dest=dest_file)
                self.device.fs.cp.assert_not_called()
                self.assertIsNone(result)

            with self.subTest("copy successful"):
                # First False because file does not already exist, then emulate device returning the wrong checksum while the file syncs
                mock_verify_file.side_effect = [False, False, True]
                mock_verify_file.reset_mock()
                result = self.device.remote_file_copy(src_file, dest=dest_file)
                self.device.fs.cp.assert_called_once_with(
                    from_path=src_file.download_url,
                    to_path=dest_file,
                    dev_timeout=src_file.timeout,
                )
                verify_file_calls = [
                    mock.call(src_file.checksum, dest_file, hashing_algorithm=src_file.hashing_algorithm)
                ]

                mock_verify_file.assert_has_calls(verify_file_calls * 3)
                self.assertIsNone(result)

            with self.subTest("copy succeeded but checksum failed"):
                self.device.fs.cp.reset_mock()
                mock_verify_file.reset_mock()
                mock_verify_file.side_effect = None
                mock_verify_file.return_value = False
                with self.assertRaises(FileTransferError):
                    result = self.device.remote_file_copy(src_file, dest=dest_file)
                self.device.fs.cp.assert_called_once_with(
                    from_path=src_file.download_url,
                    to_path=dest_file,
                    dev_timeout=src_file.timeout,
                )
                verify_file_calls = [
                    mock.call(src_file.checksum, dest_file, hashing_algorithm=src_file.hashing_algorithm)
                ]

                mock_verify_file.assert_has_calls(verify_file_calls * 6)

            with self.subTest("copy failed"):
                self.device.fs.cp.reset_mock()
                self.device.fs.cp.return_value = False
                with self.assertRaises(FileTransferError):
                    result = self.device.remote_file_copy(src_file, dest=dest_file)
                self.device.fs.cp.assert_called_once_with(
                    from_path=src_file.download_url,
                    to_path=dest_file,
                    dev_timeout=src_file.timeout,
                )

    def test_verify_file(self):
        checksum = "c0ffee"
        filename = "test.bin"
        hashing_algorithm = "sha256"

        with (
            mock.patch.object(self.device, "check_file_exists") as mock_check_file_exists,
            mock.patch.object(self.device, "compare_file_checksum") as mock_compare_file_checksum,
        ):
            with self.subTest(check_file_exists=False):
                mock_check_file_exists.return_value = False
                result = self.device.verify_file(checksum, filename, hashing_algorithm=hashing_algorithm)
                self.assertFalse(result)
            with self.subTest(check_file_exists=True, compare_file_checksum=False):
                mock_check_file_exists.return_value = True
                mock_compare_file_checksum.return_value = False
                result = self.device.verify_file(checksum, filename, hashing_algorithm=hashing_algorithm)
                self.assertFalse(result)
            with self.subTest(check_file_exists=True, compare_file_checksum=True):
                mock_compare_file_checksum.return_value = True
                result = self.device.verify_file(checksum, filename, hashing_algorithm=hashing_algorithm)
                self.assertTrue(result)


class TestJnprFreeSpace(unittest.TestCase):
    """Tests for JunOS pre-transfer free-space verification (NAPPS-1085)."""

    def setUp(self):
        self.mock_sw = mock.patch("pyntc.devices.jnpr_device.JunosNativeSW", autospec=True)
        self.mock_fs = mock.patch("pyntc.devices.jnpr_device.JunosNativeFS", autospec=True)
        self.mock_config = mock.patch("pyntc.devices.jnpr_device.JunosNativeConfig", autospec=True)
        self.mock_device = mock.patch("pyntc.devices.jnpr_device.JunosNativeDevice", autospec=True)

        self.mock_sw.start()
        self.mock_fs.start()
        self.mock_config.start()
        self.mock_device.start()

        self.device = JunosDevice("host", "user", "pass")
        self.device.native.facts = DEVICE_FACTS

    def tearDown(self):
        self.mock_sw.stop()
        self.mock_fs.stop()
        self.mock_config.stop()
        self.mock_device.stop()

    def test_get_free_space_parses_avail_format(self):
        """_get_free_space returns the bytes value parsed from the avail format string."""
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1f": {"mount": "/var/tmp", "avail": "1.0G"},
        }
        self.assertEqual(self.device._get_free_space(), 1024**3)

    def test_get_free_space_honours_file_system_argument(self):
        """_get_free_space uses the mount argument instead of the /var/tmp default."""
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1a": {"mount": "/", "avail": "500M"},
            "/dev/ad0s1f": {"mount": "/var/tmp", "avail": "1.0G"},
        }
        self.assertEqual(self.device._get_free_space(file_system="/"), 500 * 1024**2)

    def test_get_free_space_falls_back_to_root_mount(self):
        """When the requested mount is absent, fall back to the enclosing ``/`` mount."""
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1a": {"mount": "/", "avail": "500M"},
        }
        # /var/tmp is not a mount here; / is the longest prefix and wins.
        self.assertEqual(self.device._get_free_space(), 500 * 1024**2)

    def test_get_free_space_longest_prefix_match_wins(self):
        """When multiple mounts enclose the path, the most specific one wins."""
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1a": {"mount": "/", "avail": "500M"},
            "/dev/ad0s1f": {"mount": "/var", "avail": "2.0G"},
        }
        # /var/tmp is under /var (not its own mount); /var is more specific than /.
        self.assertEqual(self.device._get_free_space(), 2 * 1024**3)

    def test_get_free_space_does_not_match_prefix_that_is_not_a_directory_boundary(self):
        """A mount named ``/vari`` must not match ``/var/tmp`` as a prefix."""
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1a": {"mount": "/vari", "avail": "2.0G"},
            "/dev/ad0s1b": {"mount": "/", "avail": "500M"},
        }
        # /var/tmp must fall through to / — it does NOT live under /vari.
        self.assertEqual(self.device._get_free_space(), 500 * 1024**2)

    def test_get_free_space_raises_when_no_mount_matches(self):
        """_get_free_space raises FileSystemNotFoundError when storage_usage is empty."""
        self.device.fs.storage_usage.return_value = {}
        with self.assertRaises(FileSystemNotFoundError):
            self.device._get_free_space()

    def test_get_free_space_raises_on_unparseable_avail(self):
        """_get_free_space raises CommandError when the avail format cannot be parsed."""
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1f": {"mount": "/var/tmp", "avail": "garbage"},
        }
        with self.assertRaises(CommandError):
            self.device._get_free_space()

    @mock.patch("pyntc.devices.jnpr_device.os.path.getsize", return_value=10**12)
    @mock.patch("pyntc.devices.jnpr_device.SCP")
    def test_file_copy_raises_not_enough_free_space(self, mock_scp, _getsize):
        """file_copy raises NotEnoughFreeSpaceError and never runs SCP.put()."""
        self.device.fs.checksum.return_value = ""  # file_copy_remote_exists -> False
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1f": {"mount": "/var/tmp", "avail": "10M"},
        }
        with self.assertRaises(NotEnoughFreeSpaceError):
            self.device.file_copy("path/to/image.bin", "dest")
        mock_scp.assert_not_called()

    def test_remote_file_copy_raises_not_enough_free_space(self):
        """remote_file_copy raises NotEnoughFreeSpaceError and never invokes fs.cp."""
        self.device.fs.storage_usage.return_value = {
            "/dev/ad0s1f": {"mount": "/var/tmp", "avail": "10M"},
        }
        oversized = FileCopyModel(
            download_url="ftp://example.com/file.bin",
            checksum="c0ffee",
            file_name="file.bin",
            file_size=1,
            file_size_unit="gigabytes",
        )
        with mock.patch.object(self.device, "verify_file", return_value=False):
            with self.assertRaises(NotEnoughFreeSpaceError):
                self.device.remote_file_copy(oversized, dest="/var/tmp/file.bin")
        self.device.fs.cp.assert_not_called()

    def test_remote_file_copy_skips_space_check_when_file_size_omitted(self):
        """When FileCopyModel has no file_size, _check_free_space is NOT called."""
        self.device.fs.cp.return_value = True
        model = FileCopyModel(
            download_url="ftp://example.com/file.bin",
            checksum="c0ffee",
            file_name="file.bin",
        )
        self.assertIsNone(model.file_size_bytes)
        with (
            mock.patch.object(self.device, "verify_file", side_effect=[False, True]),
            mock.patch.object(JunosDevice, "_check_free_space") as mock_check,
        ):
            self.device.remote_file_copy(model, dest="/var/tmp/file.bin")
        mock_check.assert_not_called()
        self.device.fs.cp.assert_called_once()

    def test_remote_file_copy_appends_filename_when_url_has_no_path(self):
        """A bare ``ftp://host`` URL gets ``/<file_name>`` appended before ``fs.cp``."""
        self.device.fs.cp.return_value = True
        self.device.fs.storage_usage.return_value = STORAGE_USAGE_PLENTY
        model = FileCopyModel(
            download_url="ftp://ntc:pw@10.1.100.220",  # no path
            checksum="c0ffee",
            file_name="image.bin",
            file_size=1,
            file_size_unit="megabytes",
        )
        with mock.patch.object(self.device, "verify_file", side_effect=[False, True]):
            self.device.remote_file_copy(model, dest="/var/tmp/image.bin")
        self.device.fs.cp.assert_called_once_with(
            from_path="ftp://ntc:pw@10.1.100.220/image.bin",
            to_path="/var/tmp/image.bin",
            dev_timeout=mock.ANY,
        )

    def test_remote_file_copy_keeps_url_intact_when_path_is_present(self):
        """When the URL already contains a path, ``fs.cp`` receives it unchanged."""
        self.device.fs.cp.return_value = True
        self.device.fs.storage_usage.return_value = STORAGE_USAGE_PLENTY
        model = FileCopyModel(
            download_url="ftp://ntc:pw@10.1.100.220/subdir/image.bin",
            checksum="c0ffee",
            file_name="image.bin",
            file_size=1,
            file_size_unit="megabytes",
        )
        with mock.patch.object(self.device, "verify_file", side_effect=[False, True]):
            self.device.remote_file_copy(model, dest="/var/tmp/image.bin")
        self.device.fs.cp.assert_called_once_with(
            from_path="ftp://ntc:pw@10.1.100.220/subdir/image.bin",
            to_path="/var/tmp/image.bin",
            dev_timeout=mock.ANY,
        )


if __name__ == "__main__":
    unittest.main()
