import unittest

import mock
from netmiko.exceptions import AuthenticationException, SSHException

from pyntc.devices import IOSXRDevice, supported_devices
from pyntc.devices import iosxr_device as iosxr_module
from pyntc.errors import FileTransferError
from pyntc.utils.models import FileCopyModel

ISO = "ncs5k-golden-x-7.11.2-NTC7112.iso"
ACTIVE_VERSION = "7.11.2"
ISO_URL = "http://10.1.100.220/IOS-XR/7.11.2/{ISO}"
PROMPT = "RP/0/RP0/CPU0:ncs#"

DIR_FILE_PRESENT = f"Mon Jun 15 12:00:00.000 UTC\n\nDirectory of harddisk:\n15  -rw-  1500000000  Jun 15 12:00  {ISO}\n"
DIR_FILE_ABSENT = f"Mon Jun 15 12:00:00.000 UTC\n%Error: dir: '/harddisk:/{ISO}': No such file\n"
COPY_SUCCESS = (
    "Mon Jun 15 12:00:00.000 UTC\n"
    f"Destination filename [/harddisk:/{ISO}]?\n"
    f"Accessing http://10.1.100.220/IOS-XR/7.11.2/{ISO}\n"
    "1500000000 bytes copied in 42 secs (35714285 bytes/sec)\n"
    "RP/0/RP0/CPU0:ncs#"
)
COPY_ERROR = (
    f"Mon Jun 15 12:00:00.000 UTC\n%Error opening http://10.1.100.220/IOS-XR/7.11.2/{ISO}: Connection refused\n"
)
# Real eXR (NCS5011) copy output: netmiko strips the trailing prompt, and the
# success markers are "Successfully copied ... Bytes" / "Copy operation success".
COPY_SUCCESS_EXR = (
    f"\nAccessing http://10.1.100.220/IOS-XR/7.11.2/{ISO}\n"
    + ("!" * 60)
    + "\nSuccessfully copied 1432756224 Bytes\n\n\nCopy operation success\n"
)

SHOW_INSTALL_ACTIVE_SINGLE = (
    "Node 0/RP0/CPU0 [RP]\n"
    "  Boot Partition: xr_lv0\n"
    "  Active Packages: 1\n"
    "        ncs5k-xr-7.11.2 version=7.11.2 [Boot image]\n"
)

SHOW_INSTALL_ACTIVE_MULTI = (
    "Node 0/RP0/CPU0 [RP]\n"
    "  Active Packages: 8\n"
    "        ncs5k-xr-7.11.2 version=7.11.2 [Boot image]\n"
    "        ncs5k-isis-7.11.2\n"
    "        ncs5k-ospf-7.11.2\n"
    "        ncs5k-mpls-7.11.2\n"
    "        ncs5k-mpls-te-rsvp-7.11.2\n"
    "        ncs5k-mcast-7.11.2\n"
    "        ncs5k-m2m-7.11.2\n"
    "        ncs5k-mgbl-7.11.2\n"
)

INSTALL_ADD_RESPONSE = (
    "Mon Jun 15 12:00:00.000 UTC\n"
    "Install operation 17 started by admin:\n"
    f"  install add source harddisk:/ {ISO}\n"
    "This operation will continue asynchronously.\n"
    "Install add operation 17 will continue in the background.\n"
)

INSTALL_ADD_NO_OP_ID = "Mon Jun 15 12:00:00.000 UTC\n% Unexpected output without an operation id\n"

SHOW_FILESYSTEM_LOCATION_ALL = """
Tue Jun 23 21:22:51.023 UTC

 node:  node0_RP0_CPU0
------------------------------------------------------------------
File Systems:

      Size(b)      Free(b)        Type  Flags  Prefixes
   2358312960   2347773952  flash-disk     rw  disk0:
    480907264    479154176       flash     rw  /misc/config
  10186764288   7176835072    harddisk     rw  harddisk:
            0            0     network     rw  ftp:
            0            0     network     rw  tftp:
   3962216448   3926454272  flash-disk     rw  apphost:
"""

SHOW_INSTALL_LOG_INPROGRESS = (
    "Install operation 17: 'install add source harddisk:/ ...' started\nAction 17 in progress\n"
)

SHOW_INSTALL_LOG_SUCCESS = (
    "Install operation 17: 'install add source harddisk:/ ...' started\nInstall operation 17 completed successfully\n"
)

SHOW_INSTALL_LOG_ABORT = (
    "Install operation 17: 'install add source harddisk:/ ...' started\nInstall operation 17 aborted\n"
)

SHOW_VERSION = (
    "Cisco IOS XR Software, Version 7.11.2\n"
    "Copyright (c) 2013-2024 by Cisco Systems, Inc.\n\n"
    "cisco NCS-5011 () processor\n"
    "System uptime is 1 week, 2 days, 3 hours, 4 minutes\n"
)

DIR_HARDDISK = (
    "Mon Jun 15 12:00:00.000 UTC\n\n"
    "Directory of harddisk:\n"
    f"15  -rw-  1500000000  Jun 15 12:00  {ISO}\n\n"
    "3000000000 bytes total (2000000000 bytes free)\n"
)

DIR_HARDDISK_LOW = "Mon Jun 15 12:00:00.000 UTC\n\nDirectory of harddisk:\n3000000000 bytes total (1000 bytes free)\n"

# Real eXR (NCS5011) trailer reports kbytes, not bytes.
DIR_HARDDISK_KBYTES = (
    "Mon Jun 15 23:43:01.321 UTC\n\n"
    "Directory of harddisk:\n"
    "    13 drwxr-xr-x. 2   4096 Jun 15 20:22 .tmp\n"
    "    12 -rw-r--r--. 1 382788 Jun 15 23:35 nvgen_bkup.log\n\n"
    "9948012 kbytes total (9396256 kbytes free)\n"
)

# 'show install request' states observed on real eXR during an activation.
SHOW_INSTALL_REQUEST_IN_PROGRESS = (
    "Tue Jun 16 03:31:04.338 UTC\n"
    "User ntc, Op Id 26\ninstall activate\nncs5k-golden-x-7.11.2-NTC7112\n"
    "install operation 26 is in progress\n"
    "Install prepare operation 26 is in progress\n"
    "0/RP0                     In Progress               Partition preparation in progress\n"
)
SHOW_INSTALL_REQUEST_PENDING_RELOAD = "Tue Jun 16 03:35:12.838 UTC\nInstall operation completed, pending reload\n"
SHOW_INSTALL_REQUEST_ACTIVATE_FAILURE = (
    "Tue Jun 16 00:29:55.000 UTC\n"
    "Error: An exception is hit while executing the install operation.\n"
    "Install operation 26 aborted\n"
)

# RP/0/RP0/CPU0:NCS5011-LAB#run sha512sum /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
SHA512SUM = "30221afa665814ab68cb4dd2f114a9da2b2285b8d7b2b2854b63db7bd0a5ea7980e3d4295b8cb6bfaa3d7c4f4d8d8f635562541d727e1dd66566c4895780c47b"
RUN_SHA512SUM = f"""
Wed Jun 24 22:17:02.779 UTC
{SHA512SUM}  /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
"""

# RP/0/RP0/CPU0:NCS5011-LAB#run sha256sum /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
SHA256SUM = "71e68c6b7ff7eac595f09d34d184adf31181b16bf7d986a474277119493df8bb"
RUN_SHA256SUM = f"""
Wed Jun 24 22:17:28.194 UTC
{SHA256SUM}  /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
"""

# RP/0/RP0/CPU0:NCS5011-LAB#run sha1sum /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
SHA1SUM = "6c62c6322c796036b18fbbb819f25e6558467c51"
RUN_SHA1SUM = f"""
Wed Jun 24 22:17:47.916 UTC
{SHA1SUM}  /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
"""

# RP/0/RP0/CPU0:NCS5011-LAB#run md5sum /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
MD5SUM = "c12d35ae63203202304f0c4d5a49f0e6"
RUN_MD5SUM = f"""
Wed Jun 24 22:18:00.782 UTC
{MD5SUM}  /harddisk:/ncs5k-golden-x-7.11.1-NTC711.iso
"""


def _fake_clock(values):
    """Return a time.time() stand-in that yields ``values`` then a large constant.

    The standard ``logging`` module also calls ``time.time()``, so a finite
    ``side_effect`` list raises StopIteration unpredictably. This helper returns
    a huge value once exhausted, keeping the polling-loop timeout logic
    deterministic regardless of interleaved log calls.
    """
    seq = list(values)

    def _inner(*args, **kwargs):
        return seq.pop(0) if seq else 1e12

    return _inner


class TestIOSXRDevice(unittest.TestCase):
    @mock.patch.object(IOSXRDevice, "open")
    @mock.patch.object(IOSXRDevice, "close")
    def setUp(self, mock_close, mock_open):  # pylint: disable=arguments-differ
        self.device = IOSXRDevice("host", "user", "pass")
        self.device.native = mock.MagicMock()

    def tearDown(self):
        if self.device.native is not None:
            self.device.native.reset_mock()

    # --- basics / registration ---

    def test_port(self):
        self.assertEqual(self.device.port, 22)

    def test_device_type(self):
        self.assertEqual(self.device.device_type, "cisco_iosxr_ssh")

    def test_registration(self):
        self.assertIs(supported_devices["cisco_iosxr_ssh"], IOSXRDevice)

    # --- facts ---

    def test_os_version(self):
        self.device.native.send_command.return_value = SHOW_VERSION
        self.assertEqual(self.device.os_version, ACTIVE_VERSION)

    def test_uptime_parses_weeks(self):
        self.device.native.send_command.return_value = SHOW_VERSION
        # 1 week + 2 days + 3 hours + 4 minutes
        expected = (7 * 86400) + (2 * 86400) + (3 * 3600) + (4 * 60)
        self.assertEqual(self.device.uptime, expected)

    def test_uptime_string_folds_weeks_into_days(self):
        self.device.native.send_command.return_value = SHOW_VERSION
        # 1 week + 2 days -> 9 days, 3 hours, 4 minutes -> dd:hh:mm:ss
        self.assertEqual(self.device.uptime_string, "09:03:04:00")

    def test_hostname_strips_rp_prefix(self):
        self.device.native.find_prompt.return_value = "RP/0/RP0/CPU0:NCS5011-LAB#"
        self.assertEqual(self.device.hostname, "NCS5011-LAB")

    # --- show / config / save ---

    def test_show_list_returns_list(self):
        self.device.native.send_command.side_effect = ["out-a", "out-b"]
        self.assertEqual(self.device.show(["show foo", "show bar"]), ["out-a", "out-b"])

    def test_show_raises_command_error_on_error_response(self):
        self.device.native.send_command.return_value = "% Invalid input detected"
        with self.assertRaises(iosxr_module.CommandError):
            self.device.show("show bogus")

    def test_show_list_raises_command_list_error(self):
        self.device.native.send_command.side_effect = ["% Invalid input detected", "ok"]
        with self.assertRaises(iosxr_module.CommandListError):
            self.device.show(["show bad", "show good"])

    def test_config_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.device.config("hostname FOO")

    def test_save_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.device.save()

    # --- boot_options / install_mode / set_boot_options ---

    def test_boot_options(self):
        self.device.native.send_command.return_value = SHOW_INSTALL_ACTIVE_SINGLE
        self.assertEqual(self.device.boot_options, {"sys": "ncs5k-xr-7.11.2", "version": "7.11.2"})

    def test_boot_options_multi_package(self):
        self.device.native.send_command.return_value = SHOW_INSTALL_ACTIVE_MULTI
        self.assertEqual(self.device.boot_options, {"sys": "ncs5k-xr-7.11.2", "version": "7.11.2"})

    def test_boot_options_none_when_unmatched(self):
        self.device.native.send_command.return_value = "No active packages found"
        self.assertEqual(self.device.boot_options, {"sys": None, "version": None})

    def test_install_mode_always_true(self):
        self.assertTrue(self.device.install_mode)

    def test_set_boot_options_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.device.set_boot_options(ISO)

    # --- _image_booted ---

    def test_image_booted_true(self):
        self.device.native.send_command.return_value = SHOW_INSTALL_ACTIVE_SINGLE
        self.assertTrue(self.device._image_booted(ISO))

    def test_image_booted_false(self):
        self.device.native.send_command.return_value = SHOW_INSTALL_ACTIVE_SINGLE
        self.assertFalse(self.device._image_booted("ncs5k-mini-x-7.10.1.iso"))

    # --- _get_free_space ---

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_get_free_space(self, *_mocks):
        self.device.native.send_command.return_value = DIR_HARDDISK
        self.assertEqual(self.device._get_free_space(), 2000000000)

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_get_free_space_kbytes_units(self, *_mocks):
        self.device.native.send_command.return_value = DIR_HARDDISK_KBYTES
        self.assertEqual(self.device._get_free_space(), 9396256 * 1024)

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_get_free_space_unparsable_raises(self, *_mocks):
        self.device.native.send_command.return_value = "garbage output"
        with self.assertRaises(iosxr_module.CommandError):
            self.device._get_free_space()

    # --- async install primitives ---

    def test_install_add_parses_op_id(self):
        self.device.native.send_command.return_value = INSTALL_ADD_RESPONSE
        self.assertEqual(self.device._install_add("harddisk:/", ISO), 17)

    def test_install_add_no_op_id_raises(self):
        self.device.native.send_command.return_value = INSTALL_ADD_NO_OP_ID
        with self.assertRaises(iosxr_module.OSInstallError):
            self.device._install_add("harddisk:/", ISO)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    def test_wait_for_install_operation_success(self, mock_sleep):
        self.device.native.send_command.side_effect = [
            SHOW_INSTALL_LOG_INPROGRESS,
            SHOW_INSTALL_LOG_INPROGRESS,
            SHOW_INSTALL_LOG_SUCCESS,
        ]
        self.device._wait_for_install_operation(17)
        self.assertEqual(self.device.native.send_command.call_count, 3)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    def test_wait_for_install_operation_abort_raises(self, mock_sleep):
        self.device.native.send_command.return_value = SHOW_INSTALL_LOG_ABORT
        with self.assertRaises(iosxr_module.OSInstallError):
            self.device._wait_for_install_operation(17)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch("pyntc.devices.iosxr_device.time.time", side_effect=_fake_clock([0, 0]))
    def test_wait_for_install_operation_timeout_raises(self, mock_time, mock_sleep):
        self.device.native.send_command.return_value = SHOW_INSTALL_LOG_INPROGRESS
        with self.assertRaises(iosxr_module.OSInstallError):
            self.device._wait_for_install_operation(17, timeout=3600)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    def test_install_activate_issues_async_and_returns_on_pending_reload(self, mock_sleep):
        self.device.native.send_command_timing.return_value = "Install operation 26 started by ntc"
        self.device.native.send_command.return_value = SHOW_INSTALL_REQUEST_PENDING_RELOAD
        self.device._install_activate(25)
        self.device.native.send_command_timing.assert_any_call("install activate id 25 noprompt", read_timeout=180)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    def test_install_activate_raises_on_failure(self, mock_sleep):
        self.device.native.send_command_timing.return_value = "Install operation 26 started by ntc"
        self.device.native.send_command.return_value = SHOW_INSTALL_REQUEST_ACTIVATE_FAILURE
        with self.assertRaises(iosxr_module.OSInstallError):
            self.device._install_activate(25)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    def test_install_activate_tolerates_session_drop(self, mock_sleep):
        # The reload drops the session while polling: that is the success signal, not an error.
        self.device.native.send_command_timing.return_value = "Install operation 26 started by ntc"
        self.device.native.send_command.side_effect = OSError("socket closed")
        self.device._install_activate(25)  # must not raise

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch("pyntc.devices.iosxr_device.time.time", side_effect=_fake_clock([0, 0]))
    def test_install_activate_timeout_raises(self, mock_time, mock_sleep):
        # Activation never reaches pending-reload (status stays in progress) -> timeout -> raise.
        self.device.native.send_command_timing.return_value = "Install operation 26 started by ntc"
        self.device.native.send_command.return_value = SHOW_INSTALL_REQUEST_IN_PROGRESS
        with self.assertRaises(iosxr_module.OSInstallError):
            self.device._install_activate(25, timeout=3600)

    def test_install_commit(self):
        self.device.native.send_command.return_value = "Install operation 18 completed successfully"
        self.device._install_commit()
        self.device.native.send_command.assert_any_call("install commit", read_timeout=120)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch.object(IOSXRDevice, "open")
    def test_install_commit_retries_then_succeeds(self, mock_open, mock_sleep):
        # The install manager can be slow right after the reload; the first attempt fails.
        self.device.native.send_command.side_effect = [Exception("read timeout"), "ok"]
        self.device._install_commit()
        self.assertEqual(self.device.native.send_command.call_count, 2)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch.object(IOSXRDevice, "open")
    def test_install_commit_raises_after_exhausting_retries(self, mock_open, mock_sleep):
        self.device.native.send_command.side_effect = Exception("read timeout")
        with self.assertRaises(iosxr_module.OSInstallError):
            self.device._install_commit(retries=2)

    # --- reboot / _wait_for_device_reboot ---

    def test_reboot(self):
        self.device.reboot()
        self.device.native.send_command_timing.assert_any_call("reload")

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch.object(IOSXRDevice, "show")
    @mock.patch.object(IOSXRDevice, "open", side_effect=[None, OSError("down"), None])
    @mock.patch.object(IOSXRDevice, "close")
    def test_wait_for_device_reboot(self, mock_close, mock_open, mock_show, mock_sleep):
        # Reachable -> disconnect (reload) -> back up: requires the drop-then-recover transition.
        self.device._wait_for_device_reboot(timeout=600)
        self.assertEqual(mock_open.call_count, 3)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch("pyntc.devices.iosxr_device.time.time", side_effect=_fake_clock([0, 0]))
    @mock.patch.object(IOSXRDevice, "open", side_effect=OSError("down"))
    @mock.patch.object(IOSXRDevice, "close")
    def test_wait_for_device_reboot_timeout(self, mock_close, mock_open, mock_time, mock_sleep):
        with self.assertRaises(iosxr_module.RebootTimeoutError):
            self.device._wait_for_device_reboot(timeout=3600)

    # --- connection retry (eXR SSH rate-limit / banner race) ---

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch("pyntc.devices.iosxr_device.ConnectHandler")
    def test_connect_retries_transient_then_succeeds(self, mock_connect, mock_sleep):
        conn = mock.MagicMock()
        mock_connect.side_effect = [SSHException("Error reading SSH protocol banner"), conn]
        self.assertIs(self.device._connect(self.device._connect_attempts), conn)
        self.assertEqual(mock_connect.call_count, 2)
        mock_sleep.assert_called_once_with(self.device._connect_retry_delay)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch("pyntc.devices.iosxr_device.ConnectHandler")
    def test_connect_does_not_retry_auth_failure(self, mock_connect, mock_sleep):
        mock_connect.side_effect = AuthenticationException("bad creds")
        with self.assertRaises(AuthenticationException):
            self.device._connect(self.device._connect_attempts)
        self.assertEqual(mock_connect.call_count, 1)
        mock_sleep.assert_not_called()

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch("pyntc.devices.iosxr_device.ConnectHandler")
    def test_connect_raises_after_exhausting_attempts(self, mock_connect, mock_sleep):
        mock_connect.side_effect = SSHException("Error reading SSH protocol banner")
        with self.assertRaises(SSHException):
            self.device._connect(3)
        self.assertEqual(mock_connect.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @mock.patch("pyntc.devices.iosxr_device.time.sleep")
    @mock.patch("pyntc.devices.iosxr_device.ConnectHandler")
    def test_open_retry_false_makes_single_attempt(self, mock_connect, mock_sleep):
        # The reboot-wait loop is its own retry; each probe must fail fast.
        mock_connect.side_effect = OSError("down")
        self.device._connected = False
        with self.assertRaises(OSError):
            self.device.open(retry=False)
        self.assertEqual(mock_connect.call_count, 1)
        mock_sleep.assert_not_called()

    # --- install_os orchestration ---

    @mock.patch.object(IOSXRDevice, "uptime", new_callable=mock.PropertyMock, return_value=1000)
    @mock.patch.object(IOSXRDevice, "_image_booted", side_effect=[False, True])
    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    @mock.patch.object(IOSXRDevice, "_install_commit")
    @mock.patch.object(IOSXRDevice, "_wait_for_device_reboot")
    @mock.patch.object(IOSXRDevice, "_install_activate", return_value=18)
    @mock.patch.object(IOSXRDevice, "_wait_for_install_operation")
    @mock.patch.object(IOSXRDevice, "_install_add", return_value=17)
    def test_install_os(self, mock_add, mock_wait_op, mock_activate, mock_wait_reboot, mock_commit, *_mocks):
        result = self.device.install_os(ISO)
        self.assertTrue(result)
        mock_add.assert_called_once_with("harddisk:/", ISO)
        mock_wait_op.assert_called_once_with(17, timeout=3600)  # add op only
        mock_activate.assert_called_once_with(17, timeout=3600)
        mock_wait_reboot.assert_called_once_with(timeout=3600)
        mock_commit.assert_called_once()

    @mock.patch.object(IOSXRDevice, "_install_add")
    @mock.patch.object(IOSXRDevice, "_image_booted", return_value=True)
    def test_install_os_already_installed(self, mock_booted, mock_add):
        result = self.device.install_os(ISO)
        self.assertFalse(result)
        mock_add.assert_not_called()

    @mock.patch.object(IOSXRDevice, "_image_booted", return_value=False)
    def test_install_os_reboot_false_raises(self, mock_booted):
        with self.assertRaises(ValueError):
            self.device.install_os(ISO, reboot=False)

    @mock.patch.object(IOSXRDevice, "_install_commit")
    @mock.patch.object(IOSXRDevice, "_wait_for_device_reboot")
    @mock.patch.object(IOSXRDevice, "_install_activate", return_value=18)
    @mock.patch.object(IOSXRDevice, "_wait_for_install_operation")
    @mock.patch.object(IOSXRDevice, "_install_add", return_value=17)
    @mock.patch.object(IOSXRDevice, "uptime", new_callable=mock.PropertyMock, return_value=1000)
    @mock.patch.object(IOSXRDevice, "_image_booted", side_effect=[False, False])
    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_install_os_verify_failure_raises(self, *_mocks):
        with self.assertRaises(iosxr_module.OSInstallError):
            self.device.install_os(ISO)

    # --- check_file_exists ---

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_check_file_exists_true(self, *_mocks):
        self.device.native.send_command.return_value = DIR_FILE_PRESENT
        self.assertTrue(self.device.check_file_exists(ISO))

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_check_file_exists_false(self, *_mocks):
        self.device.native.send_command.return_value = DIR_FILE_ABSENT
        self.assertFalse(self.device.check_file_exists(ISO))

    # --- remote_file_copy ---

    def test_remote_file_copy_requires_model(self):
        with self.assertRaises(TypeError):
            self.device.remote_file_copy(ISO_URL)

    @mock.patch.object(IOSXRDevice, "check_file_exists", side_effect=[False, True])
    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_remote_file_copy_success(self, *_mocks):
        self.device.native.find_prompt.return_value = PROMPT
        self.device.native.send_command.return_value = COPY_SUCCESS
        src = FileCopyModel(download_url=ISO_URL, checksum="", file_name=ISO)

        self.device.remote_file_copy(src)

        copy_calls = [
            call
            for call in self.device.native.send_command.call_args_list
            if call.args and call.args[0].startswith("copy ")
        ]
        self.assertTrue(copy_calls)
        self.assertEqual(copy_calls[0].args[0], f"copy {ISO_URL} harddisk:/{ISO}")

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    @mock.patch.object(IOSXRDevice, "check_file_exists", return_value=True)
    def test_remote_file_copy_idempotent_when_present(self, *_mocks):
        self.device.native.find_prompt.return_value = PROMPT
        src = FileCopyModel(download_url=ISO_URL, checksum="", file_name=ISO)

        self.device.remote_file_copy(src)

        copy_calls = [
            call
            for call in self.device.native.send_command.call_args_list
            if call.args and call.args[0].startswith("copy ")
        ]
        self.assertEqual(copy_calls, [])

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    @mock.patch.object(IOSXRDevice, "check_file_exists", side_effect=[False, True])
    def test_remote_file_copy_success_exr_output(self, mock_exists, *_mocks):
        # Real eXR success output (no trailing prompt, "Successfully copied"/"Copy operation success").
        self.device.native.find_prompt.return_value = PROMPT
        self.device.native.send_command.return_value = COPY_SUCCESS_EXR
        src = FileCopyModel(download_url=ISO_URL, checksum="", file_name=ISO)

        self.device.remote_file_copy(src)  # must not raise

        self.assertEqual(mock_exists.call_count, 2)  # idempotency check + post-copy verify

    @mock.patch.object(IOSXRDevice, "check_file_exists", side_effect=[False])
    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_remote_file_copy_error_raises(self, *_mocks):
        self.device.native.find_prompt.return_value = PROMPT
        self.device.native.send_command.return_value = COPY_ERROR
        src = FileCopyModel(download_url=ISO_URL, checksum="", file_name=ISO)

        with self.assertRaises(FileTransferError):
            self.device.remote_file_copy(src)

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_get_remote_checksum_md5(self, *_mocks):
        self.device.native.send_command_timing.return_value = RUN_MD5SUM
        self.assertEqual(self.device.get_remote_checksum(ISO, hashing_algorithm="md5"), MD5SUM)

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_get_remote_checksum_sha1(self, *_mocks):
        self.device.native.send_command_timing.return_value = RUN_SHA1SUM
        self.assertEqual(self.device.get_remote_checksum(ISO, hashing_algorithm="sha1"), SHA1SUM)

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_get_remote_checksum_sha256(self, *_mocks):
        self.device.native.send_command_timing.return_value = RUN_SHA256SUM
        self.assertEqual(self.device.get_remote_checksum(ISO, hashing_algorithm="sha256"), SHA256SUM)

    @mock.patch.object(IOSXRDevice, "_get_file_system", return_value="harddisk:")
    def test_get_remote_checksum_sha512(self, *_mocks):
        self.device.native.send_command_timing.return_value = RUN_SHA512SUM
        self.assertEqual(self.device.get_remote_checksum(ISO, hashing_algorithm="sha512"), SHA512SUM)
