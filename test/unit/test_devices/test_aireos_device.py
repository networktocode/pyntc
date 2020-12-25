import json

import pytest
from unittest import mock

from pyntc.devices import AIREOSDevice
from pyntc.devices import aireos_device as aireos_module


@pytest.mark.parametrize(
    "filename,version",
    (
        ("AIR-CT5520-K9-8-8-125-0.aes", "8.8.125.0"),
        ("AIR-CT5520-8-8-125-0.aes", "8.8.125.0"),
        ("AS_5500_8_5_161_7.aes", "8.5.161.7"),
        ("AP_BUNDLE_5500_8_5_161_7.aes", "8.5.161.7"),
    ),
    ids=("encrypted", "unencrypted", "ircm", "ircm-bundle"),
)
def test_convert_filename_to_version(filename, version):
    assert aireos_module.convert_filename_to_version(filename) == version


@pytest.mark.parametrize(
    "filename,expected,image_option",
    (
        ("ap_boot_options_primary.json", True, "primary"),
        ("ap_boot_options_primary.json", False, "backup"),
        ("ap_boot_options_backup.json", True, "backup"),
        ("ap_boot_options_mixed.json", False, "primary"),
    ),
    ids=("primary-true", "primary-false", "backup-true", "mixed-false"),
)
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_ap_images_match_expected(
    mock_ap_boot_options, filename, expected, image_option, aireos_boot_image, aireos_device, aireos_mock_path
):
    with open(f"{aireos_mock_path}/{filename}") as fh:
        mock_ap_boot_options.return_value = json.load(fh)
    assert aireos_device._ap_images_match_expected(image_option, aireos_boot_image) is expected
    mock_ap_boot_options.assert_called()


@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_ap_images_pass_boot_options(mock_ap_boot_options, aireos_device, aireos_boot_image):
    ap_boot_options = {"test1": {"primary": "8.2.170.0", "backup": "8.1.170.0", "sys": "8.2.170.0"}}
    aireos_device._ap_images_match_expected("primary", aireos_boot_image, ap_boot_options)
    mock_ap_boot_options.assert_not_called()


def test_check_command_output_for_errors(aireos_device):
    command_passes = aireos_device._check_command_output_for_errors("valid command", "valid output")
    assert command_passes is None


@pytest.mark.parametrize("output", (r"Incorrect usage: invalid output", "Error: invalid output"))
def test_check_command_output_for_errors_error(output, aireos_device):
    with pytest.raises(aireos_module.CommandError) as err:
        aireos_device._check_command_output_for_errors("invalid command", output)
    assert err.value.command == "invalid command"
    assert err.value.cli_error_msg == output


def test_enter_config(aireos_device):
    aireos_device._enter_config()
    aireos_device.native.config_mode.assert_called()


@pytest.mark.parametrize(
    "filename,expected",
    (("show_sysinfo.txt", True), ("show_sysinfo_false.txt", False)),
    ids=("True", "False"),
)
def test_image_booted(aireos_show, aireos_boot_image, filename, expected):
    device = aireos_show([filename])
    image_booted = device._image_booted(aireos_boot_image)
    assert image_booted is expected


def test_send_command_timing(aireos_send_command_timing):
    command = "send_command_timing"
    device = aireos_send_command_timing([f"{command}.txt"])
    device._send_command(command)
    device.native.send_command_timing.assert_called()
    device.native.send_command_timing.assert_called_with(command)


def test_send_command_timing_kwargs(aireos_send_command_timing):
    command = "send_command_timing"
    device = aireos_send_command_timing([f"{command}.txt"])
    device._send_command(command, delay_factor=3)
    device.native.send_command_timing.assert_called()
    device.native.send_command_timing.assert_called_with(command, delay_factor=3)


def test_send_command_expect(aireos_send_command):
    command = "send_command_expect"
    device = aireos_send_command([f"{command}.txt"])
    device._send_command(command, expect_string="Continue?")
    device.native.send_command.assert_called_with("send_command_expect", expect_string="Continue?")


def test_send_command_expect_kwargs(aireos_send_command):
    command = "send_command_expect"
    device = aireos_send_command([f"{command}.txt"])
    device._send_command(command, expect_string="Continue?", delay_factor=3)
    device.native.send_command.assert_called_with("send_command_expect", expect_string="Continue?", delay_factor=3)


def test_send_command_error(aireos_send_command_timing):
    command = "send_command_error"
    device = aireos_send_command_timing([f"{command}.txt"])
    with pytest.raises(aireos_module.CommandError):
        device._send_command(command)
    device.native.send_command_timing.assert_called()


def test_uptime_components(aireos_show):
    device = aireos_show(["show_sysinfo.txt"])
    days, hours, minutes = device._uptime_components()
    assert days == 3
    assert hours == 2
    assert minutes == 20


@mock.patch.object(AIREOSDevice, "ap_image_stats", new_callable=mock.PropertyMock)
def test_wait_for_ap_image_download(mock_ap_image_stats, aireos_device):
    mock_ap_image_stats.side_effect = [
        {"count": 2, "downloaded": 0, "unsupported": 0, "failed": 0},
        {"count": 2, "downloaded": 1, "unsupported": 0, "failed": 0},
        {"count": 2, "downloaded": 2, "unsupported": 0, "failed": 0},
    ]
    aireos_device._wait_for_ap_image_download()


@pytest.mark.parametrize(
    "filename,expected_counts",
    (("ap_image_stats_unsupported.json", (1, 0)), ("ap_image_stats_failed.json", (0, 1))),
    ids=("unsupported", "failed"),
)
@mock.patch.object(AIREOSDevice, "ap_image_stats", new_callable=mock.PropertyMock)
def test_wait_for_ap_image_download_fail(
    mock_ap_image_stats, filename, expected_counts, aireos_device, aireos_mock_path
):
    with open(f"{aireos_mock_path}/{filename}") as fh:
        mock_ap_image_stats.side_effect = json.load(fh)
    with pytest.raises(aireos_module.FileTransferError) as fte:
        aireos_device._wait_for_ap_image_download()
    unsupported, failed = expected_counts
    assert fte.value.message == f"Failed transferring image to AP\nUnsupported: {unsupported}\nFailed: {failed}\n"


@mock.patch.object(AIREOSDevice, "ap_image_stats", new_callable=mock.PropertyMock)
def test_wait_for_ap_image_download_timeout(mock_ap_image_stats, aireos_device):
    mock_ap_image_stats.return_value = {"count": 2, "downloaded": 1, "unsupported": 0, "failed": 0}
    with pytest.raises(aireos_module.FileTransferError) as fte:
        aireos_device._wait_for_ap_image_download(timeout=1)
    assert fte.value.message == (
        "Failed waiting for AP image to be transferred to all devices:\n" "Total: 2\nDownloaded: 1"
    )


@mock.patch.object(AIREOSDevice, "open")
def test_wait_for_device_to_reboot(mock_open, aireos_device):
    mock_open.side_effect = [Exception, Exception, True]
    aireos_device._wait_for_device_reboot()
    mock_open.assert_has_calls([mock.call()] * 3)


@mock.patch.object(AIREOSDevice, "open")
def test_wait_for_device_to_reboot_error(mock_open, aireos_device):
    mock_open.side_effect = [Exception]
    with pytest.raises(aireos_module.RebootTimeoutError):
        aireos_device._wait_for_device_reboot(1)


@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_wait_for_peer_to_form(mock_peer_redundancy_state, aireos_device):
    mock_peer_redundancy_state.side_effect = ["n/a", "disabled", "standby hot"]
    aireos_device._wait_for_peer_to_form("standby hot")
    mock_peer_redundancy_state.assert_has_calls([mock.call()] * 3)


@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_wait_for_peer_to_form_error(mock_peer_redundancy_state, aireos_device):
    mock_peer_redundancy_state.return_value = "disabled"
    with pytest.raises(aireos_module.PeerFailedToFormError):
        aireos_device._wait_for_peer_to_form("standby hot", timeout=1)


@pytest.mark.parametrize(
    "output_filename,expected_filename",
    (
        ("show_ap_image_all.txt", "show_ap_image_all_boot_options.json"),
        ("show_ap_image_mixed.txt", "show_ap_image_mixed_boot_options.json"),
    ),
    ids=("same", "mixed"),
)
def test_ap_boot_options(output_filename, expected_filename, aireos_show, aireos_mock_path):
    device = aireos_show([output_filename])
    with open(f"{aireos_mock_path}/{expected_filename}") as fh:
        expected = json.load(fh)
    assert device.ap_boot_options == expected


@pytest.mark.parametrize(
    "output_filename,expected_filename",
    (
        ("show_ap_image_all.txt", "show_ap_image_all_image_stats.json"),
        ("show_ap_image_mixed.txt", "show_ap_image_mixed_image_stats.json"),
    ),
    ids=("unsupported", "failed"),
)
def test_ap_image_stats(output_filename, expected_filename, aireos_show, aireos_mock_path):
    device = aireos_show([output_filename])
    with open(f"{aireos_mock_path}/{expected_filename}") as fh:
        expected = json.load(fh)
    assert device.ap_image_stats == expected


@pytest.mark.parametrize("status", ("primary", "backup"), ids=("primary", "backup"))
def test_boot_options(aireos_show, aireos_boot_image, status):
    device = aireos_show([f"show_boot_{status}.txt"] * 2)
    boot_option = device.boot_options[status]
    assert boot_option == aireos_boot_image
    assert device.boot_options["sys"] == boot_option


def test_boot_options_no_default(aireos_show):
    device = aireos_show(["show_boot_no_default.txt"] * 3)
    assert device.boot_options["primary"] == "8.5.110.0"
    assert device.boot_options["backup"] == "8.2.170.0"
    assert device.boot_options["sys"] is None


def test_boot_options_none(aireos_show):
    device = aireos_show([""])
    assert device.boot_options["sys"] is None


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_pass_string(mock_enter_config, mock_check_for_errors, aireos_config):
    command = "boot primary"
    device = aireos_config([""])
    result = device.config(command)

    assert isinstance(result, str)  # TODO: Change to list when deprecating config_list
    mock_enter_config.assert_called_once()
    mock_check_for_errors.assert_called_with(command, result)
    mock_check_for_errors.assert_called_once()
    device.native.send_config_set.assert_called_with(command, enter_config_mode=False, exit_config_mode=False)
    device.native.send_config_set.assert_called_once()
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_pass_list(mock_enter_config, mock_check_for_errors, aireos_config):
    command = ["interface hostname virtual wlc1.site.com", "config interface vlan airway 20"]
    device = aireos_config(["", ""])
    result = device.config(command)

    assert isinstance(result, list)
    assert len(result) == 2
    mock_enter_config.assert_called_once()
    mock_check_for_errors.assert_has_calls(mock.call(command[index], result[index]) for index in range(2))
    device.native.send_config_set.assert_has_calls(
        mock.call(cmd, enter_config_mode=False, exit_config_mode=False) for cmd in command
    )
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_pass_netmiko_args(mock_enter_config, mock_check_for_errors, aireos_config):
    command = ["a"]
    device = aireos_config([1])
    netmiko_args = {"strip_prompt": True}
    device.config(command, **netmiko_args)

    device.native.send_config_set.assert_called_with(
        command[0], enter_config_mode=False, exit_config_mode=False, strip_prompt=True
    )


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_pass_invalid_netmiko_args(mock_enter_config, mock_check_for_errors, aireos_config):
    error_message = "send_config_set() got an unexpected keyword argument 'invalid_arg'"
    device = aireos_config([TypeError(error_message)])
    netmiko_args = {"invalid_arg": True}
    with pytest.raises(TypeError) as error:
        device.config("command", **netmiko_args)

    assert error.value.args[0] == (f"Netmiko Driver's {error_message}")
    mock_check_for_errors.assert_not_called()
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_disable_enter_config(mock_enter_config, mock_check_for_errors, aireos_config):
    command = ["a"]
    config_effects = [1]
    device = aireos_config(config_effects)
    device.config(command, enter_config_mode=False)

    device.native.send_config_set.assert_called_with(command[0], enter_config_mode=False, exit_config_mode=False)
    mock_enter_config.assert_not_called()
    device.native.exit_config_mode.assert_called_once()


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_disable_exit_config(mock_enter_config, mock_check_for_errors, aireos_config):
    command = ["a"]
    config_effects = [1]
    device = aireos_config(config_effects)
    device.config(command, exit_config_mode=False)

    device.native.send_config_set.assert_called_with(command[0], enter_config_mode=False, exit_config_mode=False)
    mock_enter_config.assert_called_once()
    device.native.exit_config_mode.assert_not_called()


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_pass_invalid_string_command(mock_enter_config, mock_check_for_errors, aireos_config):
    command = "invalid command"
    result = "Incorrect usage. invalid output"
    mock_check_for_errors.side_effect = [aireos_module.CommandError(command, result)]
    device = aireos_config(result)
    with pytest.raises(aireos_module.CommandError) as err:
        device.config(command)

    device.native.send_config_set.assert_called_with(command, enter_config_mode=False, exit_config_mode=False)
    mock_check_for_errors.assert_called_once()
    device.native.exit_config_mode.assert_called_once()
    assert err.value.command == command
    assert err.value.cli_error_msg == result


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_pass_invalid_list_command(mock_enter_config, mock_check_for_errors, aireos_config):
    mock_check_for_errors.side_effect = [
        "valid output",
        aireos_module.CommandError("invalid command", "Incorrect usage. invalid output"),
    ]
    command = ["valid command", "invalid command", "another valid command"]
    result = ["valid output", "Incorrect usage. invalid output"]
    device = aireos_config(result)
    with pytest.raises(aireos_module.CommandListError) as err:
        device.config(command)

    device.native.send_config_set.assert_has_calls(
        (
            mock.call(command[0], enter_config_mode=False, exit_config_mode=False),
            mock.call(command[1], enter_config_mode=False, exit_config_mode=False),
        )
    )
    assert (
        mock.call(command[2], enter_config_mode=False, exit_config_mode=False)
        not in device.native.send_config_set.call_args_list
    )
    mock_check_for_errors.assert_called_with(command[1], result[1])
    device.native.exit_config_mode.assert_called_once()
    assert err.value.commands == command[:2]
    assert err.value.command == command[1]


@mock.patch.object(AIREOSDevice, "config")
def test_config_list(mock_config, aireos_device):
    config_commands = ["a", "b"]
    aireos_device.config_list(config_commands)
    mock_config.assert_called_with(config_commands)


@mock.patch.object(AIREOSDevice, "config")
def test_config_list_pass_netmiko_args(mock_config, aireos_device):
    config_commands = ["a", "b"]
    aireos_device.config_list(config_commands, strip_prompt=True)
    mock_config.assert_called_with(config_commands, strip_prompt=True)


@mock.patch.object(AIREOSDevice, "is_active")
@mock.patch.object(AIREOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
def test_confirm_is_active(mock_redundancy_state, mock_is_active, aireos_device):
    mock_is_active.return_value = True
    actual = aireos_device.confirm_is_active()
    assert actual is True
    mock_redundancy_state.assert_not_called()


@mock.patch.object(AIREOSDevice, "is_active")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "close")
@mock.patch.object(AIREOSDevice, "open")
@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
def test_confirm_is_active_not_active(
    mock_connect_handler, mock_open, mock_close, mock_redundancy_state, mock_peer_redundancy_state, mock_is_active
):
    mock_is_active.return_value = False
    mock_redundancy_state.return_value = "standby hot"
    device = AIREOSDevice("host", "user", "password")
    with pytest.raises(aireos_module.DeviceNotActiveError):
        device.confirm_is_active()

    mock_redundancy_state.assert_called_once()
    mock_peer_redundancy_state.assert_called_once()
    mock_close.assert_called_once()


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_connected_getter(expected, aireos_device):
    aireos_device._connected = expected
    assert aireos_device.connected is expected


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_connected_setter(expected, aireos_device):
    aireos_device._connected = not expected
    assert aireos_device._connected is not expected
    aireos_device.connected = expected
    assert aireos_device._connected is expected


def test_close(aireos_device):
    assert aireos_device.connected
    aireos_device.close()
    aireos_device.native.disconnect.assert_called_once()
    assert not aireos_device.connected


def test_close_not_connected(aireos_device):
    aireos_device.connected = False
    assert not aireos_device.connected
    aireos_device.close()
    assert not aireos_device.connected
    aireos_device.native.disconnect.assert_not_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all(mock_disabled_wlans, mock_wlans, mock_config, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.side_effect = [[], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.disable_wlans("all")
    mock_wlans.assert_called()
    mock_config.assert_called_with(["wlan disable all"])


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all_already_disabled(
    mock_disabled_wlans, mock_wlans, mock_config, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.return_value = [5, 15, 16, 20, 21, 22, 24]
    aireos_device.disable_wlans("all")
    mock_config.assert_not_called()


@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all_fail(mock_disabled_wlans, mock_wlans, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.return_value = [16, 21, 24]
    with pytest.raises(aireos_module.WLANDisableError) as disable_err:
        aireos_device.disable_wlans("all")

    assert disable_err.value.message == (
        "Unable to disable WLAN IDs on host\n" "Expected: [5, 15, 16, 20, 21, 22, 24]\n" "Found:    [16, 21, 24]\n"
    )


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all_partially_disabled(
    mock_disabled_wlans, mock_wlans, mock_config, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.side_effect = [[16, 21, 24], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.disable_wlans("all")
    mock_wlans.assert_called()
    mock_config.assert_called_with(["wlan disable all"])


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset(mock_disabled_wlans, mock_wlans, mock_config, aireos_device):
    mock_disabled_wlans.side_effect = [[16, 21, 24], [15, 16, 21, 22, 24]]
    aireos_device.disable_wlans([15, 22])
    mock_wlans.assert_not_called()
    mock_config.assert_called_with(["wlan disable 15", "wlan disable 22"])


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset_already_disabled(mock_disabled_wlans, mock_config, aireos_device):
    mock_disabled_wlans.return_value = [16, 21, 24]
    aireos_device.disable_wlans([16, 21])
    mock_config.assert_not_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset_fail(mock_disabled_wlans, mock_config, aireos_device):
    mock_disabled_wlans.return_value = [16, 21, 24]
    with pytest.raises(aireos_module.WLANDisableError) as disable_err:
        aireos_device.disable_wlans([15])

    assert disable_err.value.message == (
        "Unable to disable WLAN IDs on host\n" "Expected: [15, 16, 21, 24]\n" "Found:    [16, 21, 24]\n"
    )


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset_partially_disabled(mock_disabled_wlans, mock_wlans, mock_config, aireos_device):
    mock_disabled_wlans.side_effect = [[16, 21, 24], [15, 16, 21, 24]]
    aireos_device.disable_wlans([15, 21])
    mock_wlans.assert_not_called()
    mock_config.assert_called_with(["wlan disable 15"])


@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
def test_disabled_wlans(mock_wlans, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    assert aireos_device.disabled_wlans == [16, 21, 24]


def test_enable_from_disable(aireos_device):
    aireos_device.native.check_enable_mode.side_effect = [False]
    aireos_device.native.check_config_mode.side_effect = [False]
    aireos_device.enable()
    aireos_device.native.enable.assert_called()
    aireos_device.native.exit_config_mode.assert_not_called()


def test_enable_from_enable(aireos_device):
    aireos_device.native.check_enable_mode.side_effect = [True]
    aireos_device.native.check_config_mode.side_effect = [False]
    aireos_device.enable()
    aireos_device.native.enable.assert_not_called()
    aireos_device.native.exit_config_mode.assert_not_called()


def test_enable_from_config(aireos_device):
    aireos_device.native.check_enable_mode.side_effect = [True]
    aireos_device.native.check_config_mode.side_effect = [True]
    aireos_device.enable()
    aireos_device.native.enable.assert_not_called()
    aireos_device.native.exit_config_mode.assert_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all(mock_enabled_wlans, mock_wlans, mock_config, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.side_effect = [[], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.enable_wlans("all")
    mock_wlans.assert_called()
    mock_config.assert_called_with(["wlan enable all"])


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all_already_enabled(
    mock_enabled_wlans, mock_wlans, mock_config, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.return_value = [5, 15, 16, 20, 21, 22, 24]
    aireos_device.enable_wlans("all")
    mock_config.assert_not_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all_fail(mock_enabled_wlans, mock_wlans, mock_config, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.return_value = [5, 15, 20, 22]
    with pytest.raises(aireos_module.WLANEnableError) as enable_err:
        aireos_device.enable_wlans("all")

    assert enable_err.value.message == (
        "Unable to enable WLAN IDs on host\n" "Expected: [5, 15, 16, 20, 21, 22, 24]\n" "Found:    [5, 15, 20, 22]\n"
    )


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all_partially_enabled(
    mock_enabled_wlans, mock_wlans, mock_config, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.side_effect = [[5, 15, 20, 22], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.enable_wlans("all")
    mock_wlans.assert_called()
    mock_config.assert_called_with(["wlan enable all"])


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset(mock_enabled_wlans, mock_wlans, mock_config, aireos_device):
    mock_enabled_wlans.side_effect = [[5, 15, 20, 22], [5, 15, 16, 21, 22]]
    aireos_device.enable_wlans([16, 21])
    mock_wlans.assert_not_called()
    mock_config.assert_called_with(["wlan enable 16", "wlan enable 21"])


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset_already_enabled(mock_enabled_wlans, mock_config, aireos_device):
    mock_enabled_wlans.return_value = [5, 15, 20, 22]
    aireos_device.enable_wlans([5, 15])
    mock_config.assert_not_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset_fail(mock_enabled_wlans, mock_config, aireos_device):
    mock_enabled_wlans.return_value = [5, 15, 20, 22]
    with pytest.raises(aireos_module.WLANEnableError) as enable_err:
        aireos_device.enable_wlans([16])

    assert enable_err.value.message == (
        "Unable to enable WLAN IDs on host\n" "Expected: [5, 15, 16, 20, 22]\n" "Found:    [5, 15, 20, 22]\n"
    )


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset_partially_enabled(mock_enabled_wlans, mock_wlans, mock_config, aireos_device):
    mock_enabled_wlans.side_effect = [[5, 15, 20, 22], [5, 15, 16, 20, 22]]
    aireos_device.enable_wlans([16, 22])
    mock_wlans.assert_not_called()
    mock_config.assert_called_with(["wlan enable 16"])


@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
def test_enabled_wlans(mock_wlans, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    assert aireos_device.enabled_wlans == [5, 15, 20, 22]


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
def test_file_copy(
    mock_boot_options, mock_convert_filename_to_version, aireos_device_path, aireos_show, aireos_send_command_timing
):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    mock_boot_options.return_value = {"primary": "8.9.0.0", "backup": "8.8.0.0", "sys": "8.9.0.0"}
    device = aireos_show([[""] * 7, "transfer_download_start_yes.txt"])
    aireos_send_command_timing(["transfer_download_start.txt"], device)
    file_copied = device.file_copy("user", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
    mock_boot_options.assert_called_once()
    mock_convert_filename_to_version.assert_called_once()
    device.show.assert_has_calls(
        [
            mock.call(
                [
                    "transfer download datatype code",
                    "transfer download mode sftp",
                    "transfer download username user",
                    "transfer download password pass",
                    "transfer download serverip 10.1.1.1",
                    "transfer download path images/",
                    "transfer download filename AIR-CT5520-K9-8-10-105-0.aes",
                ],
            ),
            mock.call("y", auto_find_prompt=False, delay_factor=10),
        ],
    )
    device.native.send_command_timing.assert_called_with("transfer download start")
    assert file_copied is True


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
def test_file_copy_config(mock_convert_filename_to_version, aireos_show, aireos_send_command_timing):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    device = aireos_show([[""] * 7])
    aireos_send_command_timing(["transfer_download_start_yes.txt"], device)
    device.file_copy("user", "pass", "10.1.1.1", "configs/host/latest.cfg", protocol="ftp", filetype="config")
    mock_convert_filename_to_version.assert_not_called()
    device.show.assert_has_calls(
        [
            mock.call(
                [
                    "transfer download datatype config",
                    "transfer download mode ftp",
                    "transfer download username user",
                    "transfer download password pass",
                    "transfer download serverip 10.1.1.1",
                    "transfer download path configs/host/",
                    "transfer download filename latest.cfg",
                ],
            ),
        ],
    )
    device.native.send_command_timing.assert_called_with("transfer download start")


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
def test_file_copy_no_copy(mock_boot_options, mock_convert_filename_to_version, aireos_device_path, aireos_show):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    device = aireos_show([])
    mock_boot_options.return_value = {"primary": "8.10.105.0", "backup": "8.8.0.0", "sys": "8.10.105.0"}
    file_copied = device.file_copy("user", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
    mock_boot_options.assert_called()
    device.show.assert_not_called()
    device.native.send_command_timing.assert_not_called()
    assert file_copied is False


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
def test_file_copy_error_setup(mock_boot_options, mock_convert_filename_to_version, aireos_show):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    mock_boot_options.return_value = {"primary": "8.8.105.0", "backup": "8.8.0.0", "sys": "8.8.105.0"}
    device = aireos_show(
        [
            aireos_module.CommandListError(
                ["transfer download datatype code", "transfer download mode"],
                "transfer download mode",
                "invalid command",
            )
        ]
    )
    with pytest.raises(aireos_module.FileTransferError) as transfer_error:
        device.file_copy("user", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
    assert transfer_error.value.message == (
        "\nCommand transfer download mode failed with message: invalid command\n"
        "Command List: \n"
        "\ttransfer download datatype code\n"
        "\ttransfer download mode\n"
    )
    device.show.assert_called_once()


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
def test_file_copy_yes_command_error(
    mock_boot_options, mock_convert_filename_to_version, aireos_show, aireos_send_command_timing
):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    mock_boot_options.return_value = {"primary": "8.8.105.0", "backup": "8.8.0.0", "sys": "8.8.105.0"}
    device = aireos_show([[""] * 7, aireos_module.CommandError("y", "Incorrect Usage: inalid command 'y'")])
    aireos_send_command_timing(["transfer_download_start.txt"])
    with pytest.raises(aireos_module.FileTransferError) as transfer_error:
        device.file_copy("user", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
    assert transfer_error.value.message == (
        f"{aireos_module.FileTransferError.default_message}\n\n"
        "Command y was not successful: Incorrect Usage: inalid command 'y'"
    )
    device.show.assert_has_calls(
        [
            mock.call(
                [
                    "transfer download datatype code",
                    "transfer download mode sftp",
                    "transfer download username user",
                    "transfer download password pass",
                    "transfer download serverip 10.1.1.1",
                    "transfer download path images/",
                    "transfer download filename AIR-CT5520-K9-8-10-105-0.aes",
                ],
            ),
            mock.call("y", auto_find_prompt=False, delay_factor=10),
        ],
    )
    device.native.send_command_timing.assert_called_with("transfer download start")


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
def test_file_copy_error_during_transfer(
    mock_boot_options, mock_convert_filename_to_version, aireos_show, aireos_send_command_timing
):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    mock_boot_options.return_value = {"primary": "8.8.105.0", "backup": "8.8.0.0", "sys": "8.8.105.0"}
    device = aireos_show([[""] * 7, aireos_module.CommandError("transfer download start", "Auth failure")])
    aireos_send_command_timing(["transfer_download_start.txt"], device)
    with pytest.raises(aireos_module.FileTransferError) as transfer_error:
        device.file_copy("invalid", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
    assert transfer_error.value.message == (
        f"{aireos_module.FileTransferError.default_message}\n\n"
        "Command transfer download start was not successful: Auth failure"
    )
    device.show.assert_has_calls(
        [
            mock.call(
                [
                    "transfer download datatype code",
                    "transfer download mode sftp",
                    "transfer download username invalid",
                    "transfer download password pass",
                    "transfer download serverip 10.1.1.1",
                    "transfer download path images/",
                    "transfer download filename AIR-CT5520-K9-8-10-105-0.aes",
                ],
            ),
            mock.call("y", auto_find_prompt=False, delay_factor=10),
        ],
    )


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
def test_file_copy_error_other(
    mock_boot_options, mock_convert_filename_to_version, aireos_show, aireos_send_command_timing
):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    mock_boot_options.return_value = {"primary": "8.8.105.0", "backup": "8.8.0.0", "sys": "8.8.105.0"}
    device = aireos_show([[""] * 7])
    aireos_send_command_timing([Exception], device)
    with pytest.raises(aireos_module.FileTransferError) as transfer_error:
        device.file_copy("invalid", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
    assert transfer_error.value.message == aireos_module.FileTransferError.default_message


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    mock_disable_wlans,
    mock_enable_wlans,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False, True])
    assert device.install_os(aireos_boot_image) is True
    device._image_booted.assert_has_calls([mock.call(aireos_boot_image)] * 2)
    mock_set_boot_options.assert_has_calls([mock.call(aireos_boot_image)])
    mock_reboot.assert_called_with(controller="both", save_config=True)
    mock_peer_redundancy_state.assert_called()
    mock_disable_wlans.assert_not_called()
    mock_enable_wlans.assert_not_called()
    mock_wait_peer.assert_called()
    mock_wait_reboot.assert_called()


def test_install_os_no_install(aireos_image_booted, aireos_boot_image):
    device = aireos_image_booted([True])
    assert device.install_os(aireos_boot_image) is False
    device._image_booted.assert_called_once()


@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_error(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False, False])
    with pytest.raises(aireos_module.OSInstallError) as boot_error:
        device.install_os(aireos_boot_image)
    assert boot_error.value.message == f"{device.host} was unable to boot into {aireos_boot_image}"
    device._image_booted.assert_has_calls([mock.call(aireos_boot_image)] * 2)


@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_error_peer(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    aireos_image_booted,
    aireos_boot_image,
):
    mock_peer_redundancy_state.side_effect = ["standby hot", "unknown"]
    mock_wait_peer.side_effect = [aireos_module.PeerFailedToFormError("host", "standby hot", "unknown")]
    device = aireos_image_booted([False, True])
    with pytest.raises(aireos_module.OSInstallError) as boot_error:
        device.install_os(aireos_boot_image)
    assert boot_error.value.message == f"{device.host}-standby was unable to boot into {aireos_boot_image}-standby hot"
    device._image_booted.assert_has_calls([mock.call(aireos_boot_image)] * 2)


@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_pass_controller(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False, True])
    assert device.install_os(aireos_boot_image, controller="self", save_config=False) is True
    mock_reboot.assert_called_with(controller="self", save_config=False)


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_all_wlans(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    mock_disable_wlans,
    mock_enable_wlans,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False, True])
    assert device.install_os(aireos_boot_image, disable_wlans="all") is True
    device._image_booted.assert_has_calls([mock.call(aireos_boot_image)] * 2)
    mock_set_boot_options.assert_has_calls([mock.call(aireos_boot_image)])
    mock_reboot.assert_called_with(controller="both", save_config=True)
    mock_peer_redundancy_state.assert_called()
    mock_disable_wlans.assert_called_with("all")
    mock_enable_wlans.assert_called_with("all")


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_select_wlans(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    mock_disable_wlans,
    mock_enable_wlans,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False, True])
    assert device.install_os(aireos_boot_image, disable_wlans=[1, 3, 7]) is True
    device._image_booted.assert_has_calls([mock.call(aireos_boot_image)] * 2)
    mock_set_boot_options.assert_has_calls([mock.call(aireos_boot_image)])
    mock_reboot.assert_called_with(controller="both", save_config=True)
    mock_peer_redundancy_state.assert_called()
    mock_disable_wlans.assert_called_with([1, 3, 7])
    mock_enable_wlans.assert_called_with([1, 3, 7])


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_wlans_error_disabling(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    mock_disable_wlans,
    mock_enable_wlans,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False])
    mock_disable_wlans.side_effect = [aireos_module.WLANDisableError(device.host, [1, 3, 7], [1, 3])]
    with pytest.raises(aireos_module.WLANDisableError):
        device.install_os(aireos_boot_image, disable_wlans=[1, 3, 7])

    device._image_booted.assert_called_once()
    mock_set_boot_options.assert_called_once()
    mock_reboot.assert_not_called()
    mock_peer_redundancy_state.assert_called_once()
    mock_enable_wlans.assert_not_called()


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_peer_to_form")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_wlans_error_enabling(
    mock_peer_redundancy_state,
    mock_wait_peer,
    mock_wait_reboot,
    mock_reboot,
    mock_set_boot_options,
    mock_disable_wlans,
    mock_enable_wlans,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False])
    mock_enable_wlans.side_effect = [aireos_module.WLANEnableError(device.host, [1, 3, 7], [1, 3])]
    with pytest.raises(aireos_module.WLANEnableError):
        device.install_os(aireos_boot_image, disable_wlans=[1, 3, 7])

    device._image_booted.assert_called_once()
    mock_set_boot_options.assert_called_once()
    mock_reboot.assert_called_once()
    mock_peer_redundancy_state.assert_called_once()


@mock.patch.object(AIREOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
@pytest.mark.parametrize(
    "redundancy_state,expected",
    (
        ("active", True),
        ("standby hot", False),
        (None, True),
    ),
    ids=("active", "standby_hot", "unsupported"),
)
def test_is_active(mock_redundancy_state, aireos_device, redundancy_state, expected):
    mock_redundancy_state.return_value = redundancy_state
    actual = aireos_device.is_active()
    assert actual is expected


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
@mock.patch.object(AIREOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_prompt_found(mock_connected, mock_connect_handler, aireos_device):
    mock_connected.return_value = True
    aireos_device.open()
    assert aireos_device._connected is True
    aireos_device.native.find_prompt.assert_called()
    mock_connect_handler.assert_not_called()
    mock_connected.assert_has_calls((mock.call(), mock.call()))


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
@mock.patch.object(AIREOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_prompt_not_found(mock_connected, mock_connect_handler, aireos_device):
    mock_connected.side_effect = [True, False]
    aireos_device.native.find_prompt.side_effect = [Exception]
    aireos_device.open()
    assert aireos_device._connected is True
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_called()


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
@mock.patch.object(AIREOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_not_connected(mock_connected, mock_connect_handler, aireos_device):
    mock_connected.return_value = False
    aireos_device._connected = False
    aireos_device.open()
    assert aireos_device._connected is True
    aireos_device.native.find_prompt.assert_not_called()
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_called()


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
@mock.patch.object(AIREOSDevice, "connected", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "confirm_is_active")
def test_open_standby(mock_confirm, mock_connected, mock_connect_handler, aireos_device):
    mock_connected.side_effect = [False, False, True]
    mock_confirm.side_effect = [aireos_module.DeviceNotActiveError("host1", "standby", "active")]
    with pytest.raises(aireos_module.DeviceNotActiveError):
        aireos_device.open()

    aireos_device.native.find_prompt.assert_not_called()
    mock_connect_handler.assert_called()
    mock_connected.assert_has_calls((mock.call(),) * 2)


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy_summary_sso_enabled", "standby hot"),
        ("show_redundancy_summary_standby", "active"),
        ("show_redundancy_summary_standalone", "disabled"),
    ),
    ids=("standby_hot", "active", "disabled"),
)
def test_peer_redundancy_state(filename, expected, aireos_show):
    device = aireos_show([f"{filename}.txt"])
    assert device.peer_redundancy_state == expected


def test_peer_redundancy_state_unsupported(aireos_show):
    device = aireos_show([aireos_module.CommandError("show redundancy summary", "unsupported")])
    assert device.peer_redundancy_state is None


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy_summary_sso_enabled", "STANDBY HOT"),
        ("show_redundancy_summary_standby", "ACTIVE"),
        ("show_redundancy_summary_standalone", "N/A"),
    ),
    ids=("standby_hot", "active", "standalone"),
)
def test_re_peer_redundancy_state(filename, expected, aireos_mock_path):
    with open(f"{aireos_mock_path}/{filename}.txt") as fh:
        show_redundancy = fh.read()
    re_redundancy_state = aireos_module.RE_PEER_REDUNDANCY_STATE.search(show_redundancy)
    actual = re_redundancy_state.group(1)
    assert actual == expected


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy_summary_sso_enabled", "ACTIVE"),
        ("show_redundancy_summary_standby", "STANDBY HOT"),
        ("show_redundancy_summary_standalone", "ACTIVE"),
    ),
    ids=("active", "standby_hot", "standalone"),
)
def test_re_redundancy_state(filename, expected, aireos_mock_path):
    with open(f"{aireos_mock_path}/{filename}.txt") as fh:
        show_redundancy = fh.read()
    re_redundancy_state = aireos_module.RE_REDUNDANCY_STATE.search(show_redundancy)
    actual = re_redundancy_state.group(1)
    assert actual == expected


@mock.patch("pyntc.devices.aireos_device.RebootSignal")
@mock.patch.object(AIREOSDevice, "save")
def test_reboot_confirm(mock_save, mock_reboot, aireos_send_command_timing, aireos_redundancy_mode_path):
    device = aireos_send_command_timing(["reset_system_confirm.txt", "reset_system_restart.txt"])
    with mock.patch(aireos_redundancy_mode_path, new_callable=mock.PropertyMock) as redundnacy_mode:
        redundnacy_mode.return_value = "sso enabled"
        device.reboot()
    device.native.send_command_timing.assert_has_calls([mock.call("reset system self"), mock.call("y")])
    mock_save.assert_called()


@mock.patch("pyntc.devices.aireos_device.RebootSignal")
@mock.patch.object(AIREOSDevice, "save")
def test_reboot_confirm_args(mock_save, mock_reboot, aireos_send_command_timing, aireos_redundancy_mode_path):
    device = aireos_send_command_timing(
        ["reset_system_save.txt", "reset_system_confirm.txt", "reset_system_restart.txt"]
    )
    with mock.patch(aireos_redundancy_mode_path, new_callable=mock.PropertyMock) as redundnacy_mode:
        redundnacy_mode.return_value = "sso enabled"
        device.reboot(timer="00:00:10", controller="both", save_config=False)
    device.native.send_command_timing.assert_has_calls(
        [mock.call("reset system both in 00:00:10"), mock.call("n"), mock.call("y")]
    )
    mock_save.assert_not_called()


@mock.patch("pyntc.devices.aireos_device.RebootSignal")
@mock.patch.object(AIREOSDevice, "save")
def test_reboot_confirm_standalone(mock_save, mock_reboot, aireos_send_command_timing, aireos_redundancy_mode_path):
    device = aireos_send_command_timing(["reset_system_confirm.txt", "reset_system_restart.txt"])
    with mock.patch(aireos_redundancy_mode_path, new_callable=mock.PropertyMock) as redundnacy_mode:
        redundnacy_mode.return_value = "sso disabled"
        device.reboot()
    device.native.send_command_timing.assert_has_calls([mock.call("reset system"), mock.call("y")])
    mock_save.assert_called()


@mock.patch("pyntc.devices.aireos_device.RebootSignal")
@mock.patch.object(AIREOSDevice, "save")
def test_reboot_confirm_standalone_args(
    mock_save, mock_reboot, aireos_send_command_timing, aireos_redundancy_mode_path
):
    device = aireos_send_command_timing(
        ["reset_system_save.txt", "reset_system_confirm.txt", "reset_system_restart.txt"]
    )
    with mock.patch(aireos_redundancy_mode_path, new_callable=mock.PropertyMock) as redundnacy_mode:
        redundnacy_mode.return_value = "sso disabled"
        device.reboot(timer="00:00:10", controller="both", save_config=False)
    device.native.send_command_timing.assert_has_calls(
        [mock.call("reset system in 00:00:10"), mock.call("n"), mock.call("y")]
    )
    mock_save.assert_not_called()


def test_redundancy_mode_sso(aireos_show):
    device = aireos_show(["show_redundancy_summary_sso_enabled.txt"])
    assert device.redundancy_mode == "sso enabled"


def test_redundancy_mode_standalone(aireos_show):
    device = aireos_show(["show_redundancy_summary_standalone.txt"])
    assert device.redundancy_mode == "sso disabled"


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy_summary_sso_enabled", "active"),
        ("show_redundancy_summary_standby", "standby hot"),
        ("show_redundancy_summary_standalone", "active"),
    ),
    ids=("active", "standby_hot", "disabled"),
)
def test_redundancy_state(filename, expected, aireos_show):
    device = aireos_show([f"{filename}.txt"])
    assert device.redundancy_state == expected


def test_redundancy_state_unsupported(aireos_show):
    device = aireos_show([aireos_module.CommandError("show redundancy summary", "unsupported")])
    assert device.redundancy_state is None


def test_save(aireos_device):
    save = aireos_device.save()
    aireos_device.native.save_config.assert_called()
    assert save is True


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "save")
def test_set_boot_options_primary(mock_save, mock_config, aireos_device, aireos_boot_image, aireos_boot_path):
    with mock.patch(aireos_boot_path, new_callable=mock.PropertyMock) as boot_options:
        boot_options.return_value = {"sys": aireos_boot_image, "primary": aireos_boot_image}
        aireos_device.set_boot_options(aireos_boot_image)
    mock_config.assert_called_with("boot primary")
    mock_save.assert_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "save")
def test_set_boot_options_backup(mock_save, mock_config, aireos_device, aireos_boot_image, aireos_boot_path):
    with mock.patch(aireos_boot_path, new_callable=mock.PropertyMock) as boot_options:
        boot_options.return_value = {
            "primary": "1",
            "backup": aireos_boot_image,
            "sys": aireos_boot_image,
        }
        aireos_device.set_boot_options(aireos_boot_image)
    mock_config.assert_called_with("boot backup")
    mock_save.assert_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "save")
def test_set_boot_options_image_not_an_option(
    mock_save, mock_config, aireos_device, aireos_boot_image, aireos_boot_path
):
    with mock.patch(aireos_boot_path, new_callable=mock.PropertyMock) as boot_options:
        boot_options.return_value = {"primary": "1", "backup": "2"}
        with pytest.raises(aireos_module.NTCFileNotFoundError) as fnfe:
            aireos_device.set_boot_options(aireos_boot_image)
            expected = f"{aireos_boot_image} was not found in 'show boot' on {aireos_device.host}"
            assert fnfe.message == expected
    mock_config.assert_not_called()
    mock_save.assert_not_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "save")
def test_set_boot_options_error(mock_save, mock_config, aireos_device, aireos_boot_image, aireos_boot_path):
    with mock.patch(aireos_boot_path, new_callable=mock.PropertyMock) as boot_options:
        boot_options.return_value = {"primary": aireos_boot_image, "backup": "2", "sys": "1"}
        with pytest.raises(aireos_module.CommandError) as ce:
            aireos_device.set_boot_options(aireos_boot_image)
            assert ce.command == "boot primary"
    mock_config.assert_called()
    mock_save.assert_called()


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_string(mock_check_for_errors, aireos_send_command):
    command = "send command"
    device = aireos_send_command([f"{command.replace(' ', '_')}.txt"])
    result = device.show(command)
    assert isinstance(result, str)
    mock_check_for_errors.assert_called_once()
    mock_check_for_errors.assert_called_with(command, result)
    device.native.send_command.assert_called_with("send command")


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_list(mock_check_for_errors, aireos_send_command):
    command = ["send command", "send command also"]
    device = aireos_send_command([f"{cmd.replace(' ', '_')}.txt" for cmd in command])
    result = device.show(command)
    assert isinstance(result, list)
    assert len(result) == 2
    assert "also" not in result[0]
    assert "also" in result[1]
    mock_check_for_errors.assert_has_calls([mock.call(command[index], result[index]) for index in range(2)])
    device.native.send_command.assert_has_calls(
        [
            mock.call("send command"),
            mock.call("send command also"),
        ]
    )


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_netmiko_args(mock_check_for_errors, aireos_send_command):
    command = "send command"
    device = aireos_send_command([""])
    netmiko_args = {"auto_find_prompt": False}
    device.show(command, **netmiko_args)
    device.native.send_command.assert_called_with(command, auto_find_prompt=False)


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_invalid_netmiko_args(mock_check_for_errors, aireos_send_command):
    command = "send command"
    error_message = "send_command() got an unexpected keyword argument 'invalid_arg'"
    device = aireos_send_command([TypeError(error_message)])
    netmiko_args = {"invalid_arg": True}
    with pytest.raises(TypeError) as error:
        device.show(command, **netmiko_args)

    assert error.value.args[0] == (f"Netmiko Driver's {error_message}")
    mock_check_for_errors.assert_not_called()
    device.native.send_command.assert_called_with(command, invalid_arg=True)


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_expect_string(mock_check_for_errors, aireos_send_command):
    command = "send command expect"
    expect_string = "Continue?"
    device = aireos_send_command(["send_command_expect.txt"])
    device.show(command, expect_string=expect_string)
    device.native.send_command.assert_called_with(command, expect_string=expect_string)


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_expect_string_and_netmiko_args(mock_check_for_errors, aireos_send_command):
    command = "send command expect"
    expect_string = "Continue?"
    device = aireos_send_command(["send_command_expect.txt"])
    netmiko_args = {"auto_find_prompt": False}
    device.show(command, expect_string=expect_string, **netmiko_args)
    device.native.send_command.assert_called_with(command, expect_string=expect_string, auto_find_prompt=False)


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_invalid_string_command(mock_check_for_errors, aireos_send_command):
    command = "send command error"
    result = "Incorrect usage."
    mock_check_for_errors.side_effect = [aireos_module.CommandError(command, result)]
    device = aireos_send_command([result])
    with pytest.raises(aireos_module.CommandError) as err:
        device.show(command)

    mock_check_for_errors.assert_called_once()
    assert err.value.command == command
    assert err.value.cli_error_msg == result


@mock.patch.object(AIREOSDevice, "_check_command_output_for_errors")
def test_show_pass_invalid_list_command(mock_check_for_errors, aireos_send_command):
    command = ["send command", "send command error", "command not sent"]
    result = ["Correct usage.", "Incorrect usage."]
    mock_check_for_errors.side_effect = [None, aireos_module.CommandError(command[1], result[1])]
    device = aireos_send_command(result)
    with pytest.raises(aireos_module.CommandListError) as err:
        device.show(command)

    device.native.send_command.assert_has_calls((mock.call(command[0]), mock.call(command[1])))
    assert mock.call(command[2]) not in device.native.send_command.call_args_list
    mock_check_for_errors.assert_called_with(command[1], result[1])
    assert err.value.command == command[1]
    assert err.value.commands == command[:2]


@mock.patch.object(AIREOSDevice, "show")
def test_show_list(mock_show, aireos_device):
    commands = ["a", "b"]
    aireos_device.show_list(commands)
    mock_show.assert_called_with(commands)


@mock.patch.object(AIREOSDevice, "show")
def test_show_list_pass_netmiko_args(mock_show, aireos_device):
    commands = ["a", "b"]
    netmiko_args = {"auto_find_prompt": False}
    aireos_device.show_list(commands, **netmiko_args)
    mock_show.assert_called_with(commands, auto_find_prompt=False)


@mock.patch.object(AIREOSDevice, "show")
def test_show_list_pass_expect_string(mock_show, aireos_device):
    commands = ["a", "b"]
    aireos_device.show_list(commands, expect_string="Continue?")
    mock_show.assert_called_with(commands, expect_string="Continue?")


@mock.patch.object(AIREOSDevice, "show")
def test_show_list_pass_netmiko_args_and_expect_string(mock_show, aireos_device):
    commands = ["a", "b"]
    netmiko_args = {"auto_find_prompt": False}
    aireos_device.show_list(commands, expect_string="Continue?", **netmiko_args)
    mock_show.assert_called_with(commands, expect_string="Continue?", auto_find_prompt=False)


@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_to_ap_already_active(
    mock_ap_boot_options, mock_ap_image_matches_expected, aireos_device, aireos_boot_image
):
    mock_ap_image_matches_expected.return_value = True
    assert aireos_device.transfer_image_to_ap(aireos_boot_image) is False
    mock_ap_image_matches_expected.assert_called_once()
    mock_ap_boot_options.assert_called_once()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "_wait_for_ap_image_download")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_to_ap_already_transferred_primary(
    mock_ap_boot_options,
    mock_ap_image_matches_expected,
    mock_boot_options,
    mock_wait,
    mock_config,
    aireos_device,
    aireos_mock_path,
    aireos_boot_image,
):
    mock_ap_image_matches_expected.side_effect = [False, True, False, True]
    assert aireos_device.transfer_image_to_ap(aireos_boot_image) is False
    assert len(mock_ap_image_matches_expected.mock_calls) == 4
    mock_config.assert_not_called()
    mock_wait.assert_not_called()
    mock_boot_options.assert_not_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "_wait_for_ap_image_download")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_to_ap_already_transferred_secondary(
    mock_ap_boot_options,
    mock_ap_image_matches_expected,
    mock_boot_options,
    mock_wait,
    mock_config,
    aireos_device,
    aireos_mock_path,
    aireos_boot_image,
):
    mock_ap_image_matches_expected.side_effect = [False, False, True, True, True]
    assert aireos_device.transfer_image_to_ap(aireos_boot_image) is True
    assert len(mock_ap_image_matches_expected.mock_calls) == 5
    mock_config.assert_has_calls([mock.call("ap image swap all")])
    mock_wait.assert_not_called()
    mock_boot_options.assert_not_called()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "_wait_for_ap_image_download")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_to_ap_already_transferred_secondary_fail(
    mock_ap_boot_options,
    mock_ap_image_matches_expected,
    mock_boot_options,
    mock_wait,
    mock_config,
    aireos_device,
    aireos_mock_path,
    aireos_boot_image,
):
    mock_ap_image_matches_expected.side_effect = [False, False, True, True, False]
    with pytest.raises(aireos_module.FileTransferError) as fte:
        aireos_device.transfer_image_to_ap(aireos_boot_image)
    assert len(mock_ap_image_matches_expected.mock_calls) == 5
    mock_config.assert_has_calls([mock.call("ap image swap all")])
    mock_wait.assert_not_called()
    mock_boot_options.assert_not_called()
    assert fte.value.message == f"Unable to set all APs to use {aireos_boot_image}"


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "_wait_for_ap_image_download")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_to_ap_transfer_primary(
    mock_ap_boot_options,
    mock_ap_image_matches_expected,
    mock_boot_options,
    mock_wait,
    mock_config,
    aireos_device,
    aireos_mock_path,
    aireos_boot_image,
):
    mock_boot_options.return_value = {"primary": aireos_boot_image, "backup": None}
    mock_ap_image_matches_expected.side_effect = [False, False, False, False, True]
    assert aireos_device.transfer_image_to_ap(aireos_boot_image) is True
    assert len(mock_ap_image_matches_expected.mock_calls) == 5
    mock_config.assert_has_calls([mock.call("ap image predownload primary all")])
    mock_wait.assert_called()
    mock_boot_options.assert_called_once()


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "_wait_for_ap_image_download")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_to_ap_transfer_secondary(
    mock_ap_boot_options,
    mock_ap_image_matches_expected,
    mock_boot_options,
    mock_wait,
    mock_config,
    aireos_device,
    aireos_mock_path,
    aireos_boot_image,
):
    mock_boot_options.return_value = {"primary": None, "backup": aireos_boot_image}
    mock_ap_image_matches_expected.side_effect = [False, False, False, True, True]
    assert aireos_device.transfer_image_to_ap(aireos_boot_image) is True
    assert len(mock_ap_image_matches_expected.mock_calls) == 5
    mock_config.assert_has_calls([mock.call("ap image predownload backup all"), mock.call("ap image swap all")])
    mock_wait.assert_called()
    mock_boot_options.assert_has_calls([mock.call(), mock.call()])


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "_wait_for_ap_image_download")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_to_ap_transfer_secondary_fail(
    mock_ap_boot_options,
    mock_ap_image_matches_expected,
    mock_boot_options,
    mock_wait,
    mock_config,
    aireos_device,
    aireos_mock_path,
    aireos_boot_image,
):
    mock_boot_options.return_value = {"primary": None, "backup": aireos_boot_image}
    mock_ap_image_matches_expected.side_effect = [False, False, False, True, False]
    with pytest.raises(aireos_module.FileTransferError) as fte:
        aireos_device.transfer_image_to_ap(aireos_boot_image)
    assert len(mock_ap_image_matches_expected.mock_calls) == 5
    mock_config.assert_has_calls([mock.call("ap image predownload backup all"), mock.call("ap image swap all")])
    mock_wait.assert_called()
    mock_boot_options.assert_has_calls([mock.call(), mock.call()])
    assert fte.value.message == f"Unable to set all APs to use {aireos_boot_image}"


@mock.patch.object(AIREOSDevice, "config")
@mock.patch.object(AIREOSDevice, "_wait_for_ap_image_download")
@mock.patch.object(AIREOSDevice, "boot_options", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "_ap_images_match_expected")
@mock.patch.object(AIREOSDevice, "ap_boot_options", new_callable=mock.PropertyMock)
def test_transfer_image_does_not_exist(
    mock_ap_boot_options,
    mock_ap_image_matches_expected,
    mock_boot_options,
    mock_wait,
    mock_config,
    aireos_device,
    aireos_mock_path,
    aireos_boot_image,
):
    mock_boot_options.return_value = {"primary": None, "backup": None}
    mock_ap_image_matches_expected.return_value = False
    with pytest.raises(aireos_module.FileTransferError) as fte:
        aireos_device.transfer_image_to_ap(aireos_boot_image)
    assert len(mock_ap_image_matches_expected.mock_calls) == 3
    mock_config.assert_not_called()
    mock_wait.assert_not_called()
    mock_boot_options.assert_has_calls([mock.call(), mock.call()])
    assert fte.value.message == f"Unable to find {aireos_boot_image} on {aireos_device.host}"


@mock.patch.object(AIREOSDevice, "_uptime_components")
def test_uptime(mock_uptime_components, aireos_device):
    mock_uptime_components.side_effect = [(3, 2, 20)]
    assert aireos_device.uptime == 267600


@mock.patch.object(AIREOSDevice, "_uptime_components")
def test_uptime_string(mock_uptime_components, aireos_device):
    mock_uptime_components.side_effect = [(3, 2, 20)]
    assert aireos_device.uptime_string == "03:02:20:00"


def test_wlans(aireos_show, aireos_expected_wlans):
    device = aireos_show(["show_wlan_summary.txt"])
    assert device.wlans == aireos_expected_wlans
