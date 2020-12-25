import pytest
import os
from unittest import mock

from .device_mocks.asa import send_command
from pyntc.devices import ASADevice
from pyntc.devices.asa_device import FileTransferError
from pyntc.errors import CommandError, CommandListError, NTCFileNotFoundError
from pyntc.devices import asa_device as asa_module

BOOT_IMAGE = "asa9-12-3-12-smp-k8.bin"
BOOT_OPTIONS_PATH = "pyntc.devices.asa_device.ASADevice.boot_options"
ACTIVE = "active"
STANDBY_READY = "standby ready"
NEGOTIATION = "negotiation"
FAILED = "failed"
NOT_DETECTED = "not detected"
COLD_STANDBY = "cold standby"


class TestASADevice:
    @mock.patch("pyntc.devices.asa_device.ConnectHandler")
    def setup(self, api):

        if not getattr(self, "device", None):
            self.device = ASADevice("host", "user", "password")

        # need to think if there should be an if before this...
        self.device.native = api

        # counts how many times we setup and tear down
        if not getattr(self, "count_setup", None):
            self.count_setup = 0

        if not getattr(self, "count_teardown", None):
            self.count_teardown = 0

        self.device = ASADevice("host", "user", "password")
        api.send_command_timing.side_effect = send_command
        api.send_command.side_effect = send_command
        self.device.native = api
        self.count_setup += 1

    def teardown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()
        self.count_teardown += 1

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
        command = "hostname DATA-CENTER-FW"

        result = self.device.config(command)
        assert result is None

        self.device.native.send_command_timing.assert_called_with(command)

    def test_bad_config(self):
        command = "asdf poknw"

        with pytest.raises(CommandError, match=command):
            self.device.config(command)

    def test_config_list(self):
        commands = ["crypto key generate rsa modulus 2048", "aaa authentication ssh console LOCAL"]
        self.device.config_list(commands)

        for cmd in commands:
            self.device.native.send_command_timing.assert_any_call(cmd)

    def test_bad_config_list(self):
        commands = ["crypto key generate rsa modulus 2048", "lalala"]
        results = ["ok", "Error: lalala"]

        self.device.native.send_command_timing.side_effect = results

        with pytest.raises(CommandListError, match=commands[1]):
            self.device.config_list(commands)

    def test_show(self):
        command = "show running config"
        result = self.device.show(command)

        assert isinstance(result, str)
        assert "interface" in result
        assert "inspect" in result

    def test_bad_show(self):
        command = "show linux"
        self.device.native.send_command_timing.return_value = "Error: linux"
        with pytest.raises(CommandError):
            self.device.show(command)

    def test_show_list(self):
        commands = ["show running config", "show startup-config"]

        result = self.device.show_list(commands)
        assert isinstance(result, list)
        assert "console" in result[0]
        assert "security-level" in result[1]

        calls = list(mock.call(x) for x in commands)
        self.device.native.send_command_timing.assert_has_calls(calls)

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        results = ["Error: badcommand", "14:31:57.089 PST Tue Feb 10 2008"]

        self.device.native.send_command_timing.side_effect = results

        with pytest.raises(CommandListError, match="show badcommand"):
            self.device.show_list(commands)

    def test_save(self):
        result = self.device.save()

        assert result
        self.device.native.send_command_timing.assert_any_call("copy running-config startup-config")

    @mock.patch("pyntc.devices.asa_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "disk0: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        assert result

    @mock.patch("pyntc.devices.asa_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_bad_md5(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "disk0: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = False

        result = self.device.file_copy_remote_exists("source_file")

        assert not result

    @mock.patch("pyntc.devices.asa_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_not(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "disk0: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        assert not result

    @mock.patch("pyntc.devices.asa_device.FileTransfer", autospec=True)
    def test_file_copy(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "disk0: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(self.device.native, "path/to/source_file", "source_file", file_system="disk0:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.asa_device.FileTransfer", autospec=True)
    def test_file_copy_different_dest(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "disk0: /dev/null"
        mock_ft_instance = mock_ft.return_value

        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("source_file", "dest_file")

        mock_ft.assert_called_with(self.device.native, "source_file", "dest_file", file_system="disk0:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.asa_device.FileTransfer", autospec=True)
    def test_file_copy_fail(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "disk0: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = Exception
        mock_ft_instance.check_file_exists.return_value = False

        with pytest.raises(FileTransferError):
            self.device.file_copy("source_file")

    def test_reboot(self):
        self.device.reboot()
        self.device.native.send_command_timing.assert_any_call("reload")

    def test_reboot_with_timer(self):
        self.device.reboot(timer=5)
        self.device.native.send_command_timing.assert_any_call("reload in 5")

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_boot_options_dir(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = f"Current BOOT variable = disk0:/{BOOT_IMAGE}"
        boot_options = self.device.boot_options
        assert boot_options == {"sys": BOOT_IMAGE}
        self.device.native.send_command_timing.assert_called_with("show boot | i BOOT variable")

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_boot_options_none(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = ""
        boot_options = self.device.boot_options
        assert boot_options["sys"] is None

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    @mock.patch.object(ASADevice, "config_list", return_value=None)
    def test_set_boot_options(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
            mock_cl.assert_called_with([f"boot system disk0:/{BOOT_IMAGE}"])

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    @mock.patch.object(ASADevice, "config_list", return_value=None)
    def test_set_boot_options_dir(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE, file_system="disk0:")
            mock_fs.assert_not_called()
            mock_cl.assert_called_with([f"boot system disk0:/{BOOT_IMAGE}"])

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    def test_set_boot_options_no_file(self, mock_fs):
        with pytest.raises(NTCFileNotFoundError):
            self.device.set_boot_options("bad_image.bin")

    @mock.patch.object(ASADevice, "_get_file_system", return_value="disk0:")
    @mock.patch.object(ASADevice, "config_list", return_value=None)
    def test_set_boot_options_bad_boot(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": "bad_image.bin"}
            with pytest.raises(CommandError):
                self.device.set_boot_options(BOOT_IMAGE)
                mock_boot.assert_called_once()

    def test_backup_running_config(self):
        filename = "local_running_config"
        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        assert contents == self.device.running_config
        os.remove(filename)

    def test_checkpoint(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.send_command_timing.assert_any_call("copy running-config good_checkpoint")

    def test_running_config(self):
        expected = self.device.show("show running config")
        assert self.device.running_config == expected

    def test_starting_config(self):
        expected = self.device.show("show startup-config")
        assert self.device.startup_config == expected

    def test_count_setup(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_setup == 1

    def test_count_teardown(self):
        # This class is reinstantiated in every test, so the counter is reset
        assert self.count_teardown == 0


@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_wait_for_peer_reboot(mock_peer_redundancy_state, asa_device):
    mock_peer_redundancy_state.side_effect = [STANDBY_READY, FAILED, FAILED, STANDBY_READY]
    asa_device._wait_for_peer_reboot([STANDBY_READY, COLD_STANDBY], 2)
    assert mock_peer_redundancy_state.call_count == 4


@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_wait_for_peer_reboot_never_fail_error(mock_peer_redundancy_state, asa_device):
    mock_peer_redundancy_state.return_value = STANDBY_READY
    with pytest.raises(asa_module.RebootTimeoutError):
        asa_device._wait_for_peer_reboot([STANDBY_READY, COLD_STANDBY], 2)

    assert mock_peer_redundancy_state.call_count > 1


@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_wait_for_peer_reboot_fail_state_error(mock_peer_redundancy_state, asa_device):
    mock_peer_redundancy_state.side_effect = [FAILED, FAILED, COLD_STANDBY, COLD_STANDBY]
    with pytest.raises(asa_module.RebootTimeoutError):
        asa_device._wait_for_peer_reboot([STANDBY_READY], 1)

    assert mock_peer_redundancy_state.call_count > 1


@mock.patch.object(ASADevice, "_wait_for_peer_reboot")
@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_reboot_standby(mock_peer_redundancy_state, mock_wait_for_peer_reboot, asa_show):
    mock_peer_redundancy_state.return_value = STANDBY_READY
    device = asa_show([""])
    assert device.reboot_standby() is None
    mock_peer_redundancy_state.assert_called_once()
    mock_wait_for_peer_reboot.assert_called_with(acceptable_states=[STANDBY_READY])


@mock.patch.object(ASADevice, "_wait_for_peer_reboot")
@mock.patch.object(ASADevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_reboot_standby_pass_args(mock_peer_redundancy_state, mock_wait_for_peer_reboot, asa_show):
    device = asa_show([""])
    device.reboot_standby(acceptable_states=[COLD_STANDBY, STANDBY_READY], timeout=1)
    mock_peer_redundancy_state.assert_not_called()
    mock_wait_for_peer_reboot.assert_called_with(acceptable_states=[COLD_STANDBY, STANDBY_READY], timeout=1)


@mock.patch.object(ASADevice, "_wait_for_peer_reboot")
def test_reboot_standby_error(mock_wait_for_peer_reboot, asa_show):
    device = asa_show([""])
    mock_wait_for_peer_reboot.side_effect = [asa_module.RebootTimeoutError(device.host, 1)]
    with pytest.raises(asa_module.RebootTimeoutError):
        device.reboot_standby(acceptable_states=[STANDBY_READY], timeout=1)

    mock_wait_for_peer_reboot.assert_called()


@mock.patch.object(ASADevice, "redundancy_state", new_callable=mock.PropertyMock)
@pytest.mark.parametrize(
    "redundancy_state,expected",
    (
        (ACTIVE, True),
        (STANDBY_READY, False),
        (NEGOTIATION, False),
        (FAILED, False),
        (COLD_STANDBY, False),
        (None, True),
    ),
    ids=(ACTIVE, "standby_ready", NEGOTIATION, FAILED, "cold_standby", "unsupported"),
)
def test_is_active(mock_redundancy_state, asa_device, redundancy_state, expected):
    mock_redundancy_state.return_value = redundancy_state
    actual = asa_device.is_active()
    assert actual is expected


@pytest.mark.parametrize(
    "side_effect,expected",
    (
        ("show_failover_host_active.txt", STANDBY_READY),
        ("show_failover_host_standby.txt", ACTIVE),
        ("show_failover_host_off.txt", "disabled"),
        ("show_failover_groups_active_active.txt", ACTIVE),
        ("show_failover_groups_active_standby.txt", STANDBY_READY),
        ("show_failover_groups_standby_active.txt", ACTIVE),
        ("show_failover_peer_cold.txt", COLD_STANDBY),
        ("show_failover_peer_failed.txt", FAILED),
        ("show_failover_peer_not_detected.txt", NOT_DETECTED),
        (asa_module.CommandError("show failover", r"% invalid command"), None),
    ),
    ids=(
        "standby",
        ACTIVE,
        "disabled",
        "active_active",
        "active_standby",
        "standby_active",
        COLD_STANDBY,
        FAILED,
        NOT_DETECTED,
        "none",
    ),
)
def test_peer_redundancy_state(side_effect, expected, asa_show):
    device = asa_show([side_effect])
    actual = device.peer_redundancy_state
    assert actual == expected


@pytest.mark.parametrize(
    "side_effect,expected",
    (
        ("show_failover_host_active.txt", "on"),
        ("show_failover_host_off.txt", "off"),
        (asa_module.CommandError("show failover", r"% invalid command"), "n/a"),
    ),
    ids=("on", "off", "n/a"),
)
def test_redundancy_mode(side_effect, expected, asa_show):
    device = asa_show([side_effect])
    actual = device.redundancy_mode
    assert actual == expected


@pytest.mark.parametrize(
    "side_effect,expected",
    (
        ("show_failover_host_active.txt", ACTIVE),
        ("show_failover_host_standby.txt", STANDBY_READY),
        ("show_failover_host_off.txt", "disabled"),
        ("show_failover_host_negotiation.txt", NEGOTIATION),
        ("show_failover_groups_active_active.txt", ACTIVE),
        ("show_failover_groups_active_standby.txt", ACTIVE),
        ("show_failover_groups_standby_active.txt", STANDBY_READY),
        (asa_module.CommandError("show failover", r"% invalid command"), None),
    ),
    ids=(ACTIVE, "standby", "disabled", NEGOTIATION, "active_active", "active_standby", "standby_active", "none"),
)
def test_redundancy_state(side_effect, expected, asa_show):
    device = asa_show([side_effect])
    actual = device.redundancy_state
    assert actual == expected


def test_send_command_timing(asa_send_command_timing):
    command = "send_command_timing"
    device = asa_send_command_timing([f"{command}.txt"])
    device._send_command(command)
    device.native.send_command_timing.assert_called()
    device.native.send_command_timing.assert_called_with(command)


def test_send_command_expect(asa_send_command):
    command = "send_command_expect"
    device = asa_send_command([f"{command}.txt"])
    device._send_command(command, expect_string="Continue?")
    device.native.send_command.assert_called_with("send_command_expect", expect_string="Continue?")


def test_send_command_error(asa_send_command_timing):
    command = "send_command_error"
    device = asa_send_command_timing([f"{command}.txt"])
    with pytest.raises(CommandError):
        device._send_command(command)
    device.native.send_command_timing.assert_called()
