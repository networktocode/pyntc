import json

import pytest
from unittest import mock

from pyntc.devices import AIREOSDevice
from pyntc.devices.aireos_device import (
    CommandError,
    OSInstallError,
    WLANEnableError,
    CommandListError,
    WLANDisableError,
    FileTransferError,
    RebootTimeoutError,
    NTCFileNotFoundError,
    convert_filename_to_version,
)


@pytest.mark.parametrize(
    "filename,version",
    (("AIR-CT5520-K9-8-8-125-0.aes", "8.8.125.0"), ("AIR-CT5520-8-8-125-0.aes", "8.8.125.0")),
    ids=("encrypted", "unencrypted"),
)
def test_convert_filename_to_version(filename, version):
    assert convert_filename_to_version(filename) == version


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


def test_send_command_error(aireos_send_command_timing):
    command = "send_command_error"
    device = aireos_send_command_timing([f"{command}.txt"])
    with pytest.raises(CommandError):
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
    with pytest.raises(FileTransferError) as fte:
        aireos_device._wait_for_ap_image_download()
    unsupported, failed = expected_counts
    assert fte.value.message == f"Failed transferring image to AP\nUnsupported: {unsupported}\nFailed: {failed}\n"


@mock.patch.object(AIREOSDevice, "ap_image_stats", new_callable=mock.PropertyMock)
def test_wait_for_ap_image_download_timeout(mock_ap_image_stats, aireos_device):
    mock_ap_image_stats.return_value = {"count": 2, "downloaded": 1, "unsupported": 0, "failed": 0}
    with pytest.raises(FileTransferError) as fte:
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
    with pytest.raises(RebootTimeoutError):
        aireos_device._wait_for_device_reboot(1)


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


@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config(mock_enter, aireos_send_command_timing):
    config = "interface hostname virtual wlc1.site.com"
    device = aireos_send_command_timing([config])
    device.config(config)
    mock_enter.assert_called()
    device.native.exit_config_mode.assert_called()


@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_list(mock_enter, aireos_send_command_timing):
    configs = [
        "interface hostname virtual wlc1.site.com",
        "config interface vlan airway 20",
    ]
    device = aireos_send_command_timing([""] * 2)
    device.config_list(configs)
    mock_enter.assert_called()
    device.native.exit_config_mode.assert_called()
    device.native.send_command_timing.assert_has_calls([mock.call(cmd) for cmd in configs])


@mock.patch.object(AIREOSDevice, "_enter_config")
def test_config_list_error(mock_enter, aireos_send_command_timing):
    configs = [
        "interface hostname virtual wlc1.site.com",
        "config interface vlan airway 20",
    ]
    device = aireos_send_command_timing([CommandError("interface hostname virtual wlc1.site.com", "test")])
    with pytest.raises(CommandListError):
        device.config_list(configs)

    mock_enter.assert_called()
    device.native.exit_config_mode.assert_called()
    device.native.send_command_timing.assert_called_once()


def test_connected_getter(aireos_device):
    assert aireos_device.connected in {True, False}


def test_connected_setter(aireos_device):
    aireos_device.connected = True
    assert aireos_device.connected is True
    aireos_device.connected = False
    assert aireos_device.connected is False


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


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all(mock_disabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.side_effect = [[], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.disable_wlans("all")
    mock_wlans.assert_called()
    mock_config_list.assert_called_with(["wlan disable all"])


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all_already_disabled(
    mock_disabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.return_value = [5, 15, 16, 20, 21, 22, 24]
    aireos_device.disable_wlans("all")
    mock_config_list.assert_not_called()


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all_fail(
    mock_disabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.return_value = [16, 21, 24]
    with pytest.raises(WLANDisableError) as disable_err:
        aireos_device.disable_wlans("all")

    assert disable_err.value.message == (
        "Unable to disable WLAN IDs on host\n" "Expected: [5, 15, 16, 20, 21, 22, 24]\n" "Found:    [16, 21, 24]\n"
    )


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_all_partially_disabled(
    mock_disabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_disabled_wlans.side_effect = [[16, 21, 24], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.disable_wlans("all")
    mock_wlans.assert_called()
    mock_config_list.assert_called_with(["wlan disable all"])


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset(mock_disabled_wlans, mock_wlans, mock_config_list, aireos_device):
    mock_disabled_wlans.side_effect = [[16, 21, 24], [15, 16, 21, 22, 24]]
    aireos_device.disable_wlans([15, 22])
    mock_wlans.assert_not_called()
    mock_config_list.assert_called_with(["wlan disable 15", "wlan disable 22"])


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset_already_disabled(mock_disabled_wlans, mock_config_list, aireos_device):
    mock_disabled_wlans.return_value = [16, 21, 24]
    aireos_device.disable_wlans([16, 21])
    mock_config_list.assert_not_called()


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset_fail(mock_disabled_wlans, mock_config_list, aireos_device):
    mock_disabled_wlans.return_value = [16, 21, 24]
    with pytest.raises(WLANDisableError) as disable_err:
        aireos_device.disable_wlans([15])

    assert disable_err.value.message == (
        "Unable to disable WLAN IDs on host\n" "Expected: [15, 16, 21, 24]\n" "Found:    [16, 21, 24]\n"
    )


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "disabled_wlans", new_callable=mock.PropertyMock)
def test_disable_wlans_subset_partially_disabled(mock_disabled_wlans, mock_wlans, mock_config_list, aireos_device):
    mock_disabled_wlans.side_effect = [[16, 21, 24], [15, 16, 21, 24]]
    aireos_device.disable_wlans([15, 21])
    mock_wlans.assert_not_called()
    mock_config_list.assert_called_with(["wlan disable 15"])


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


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all(mock_enabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.side_effect = [[], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.enable_wlans("all")
    mock_wlans.assert_called()
    mock_config_list.assert_called_with(["wlan enable all"])


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all_already_enabled(
    mock_enabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.return_value = [5, 15, 16, 20, 21, 22, 24]
    aireos_device.enable_wlans("all")
    mock_config_list.assert_not_called()


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all_fail(mock_enabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.return_value = [5, 15, 20, 22]
    with pytest.raises(WLANEnableError) as enable_err:
        aireos_device.enable_wlans("all")

    assert enable_err.value.message == (
        "Unable to enable WLAN IDs on host\n" "Expected: [5, 15, 16, 20, 21, 22, 24]\n" "Found:    [5, 15, 20, 22]\n"
    )


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_all_partially_enabled(
    mock_enabled_wlans, mock_wlans, mock_config_list, aireos_device, aireos_expected_wlans
):
    mock_wlans.return_value = aireos_expected_wlans
    mock_enabled_wlans.side_effect = [[5, 15, 20, 22], [5, 15, 16, 20, 21, 22, 24]]
    aireos_device.enable_wlans("all")
    mock_wlans.assert_called()
    mock_config_list.assert_called_with(["wlan enable all"])


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset(mock_enabled_wlans, mock_wlans, mock_config_list, aireos_device):
    mock_enabled_wlans.side_effect = [[5, 15, 20, 22], [5, 15, 16, 21, 22]]
    aireos_device.enable_wlans([16, 21])
    mock_wlans.assert_not_called()
    mock_config_list.assert_called_with(["wlan enable 16", "wlan enable 21"])


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset_already_enabled(mock_enabled_wlans, mock_config_list, aireos_device):
    mock_enabled_wlans.return_value = [5, 15, 20, 22]
    aireos_device.enable_wlans([5, 15])
    mock_config_list.assert_not_called()


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset_fail(mock_enabled_wlans, mock_config_list, aireos_device):
    mock_enabled_wlans.return_value = [5, 15, 20, 22]
    with pytest.raises(WLANEnableError) as enable_err:
        aireos_device.enable_wlans([16])

    assert enable_err.value.message == (
        "Unable to enable WLAN IDs on host\n" "Expected: [5, 15, 16, 20, 22]\n" "Found:    [5, 15, 20, 22]\n"
    )


@mock.patch.object(AIREOSDevice, "config_list")
@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
@mock.patch.object(AIREOSDevice, "enabled_wlans", new_callable=mock.PropertyMock)
def test_enable_wlans_subset_partially_enabled(mock_enabled_wlans, mock_wlans, mock_config_list, aireos_device):
    mock_enabled_wlans.side_effect = [[5, 15, 20, 22], [5, 15, 16, 20, 22]]
    aireos_device.enable_wlans([16, 22])
    mock_wlans.assert_not_called()
    mock_config_list.assert_called_with(["wlan enable 16"])


@mock.patch.object(AIREOSDevice, "wlans", new_callable=mock.PropertyMock)
def test_enabled_wlans(mock_wlans, aireos_device, aireos_expected_wlans):
    mock_wlans.return_value = aireos_expected_wlans
    assert aireos_device.enabled_wlans == [5, 15, 20, 22]


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
def test_file_copy(
    mock_convert_filename_to_version, aireos_device_path, aireos_send_command_timing, aireos_send_command
):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    device = aireos_send_command_timing([""] * 7 + ["transfer_download_start.txt"])
    aireos_send_command(["transfer_download_start_yes.txt"], device)
    with mock.patch(f"{aireos_device_path}.boot_options", new_callable=mock.PropertyMock) as mock_boot_optionsot:
        mock_boot_optionsot.return_value = {"primary": "8.9.0.0", "backup": "8.8.0.0", "sys": "8.9.0.0"}
        file_copied = device.file_copy("user", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
        mock_boot_optionsot.assert_called_once()
    mock_convert_filename_to_version.assert_called_once()
    device.native.send_command_timing.assert_has_calls(
        [
            mock.call("transfer download datatype code"),
            mock.call("transfer download mode sftp"),
            mock.call("transfer download username user"),
            mock.call("transfer download password pass"),
            mock.call("transfer download serverip 10.1.1.1"),
            mock.call("transfer download path images/"),
            mock.call("transfer download filename AIR-CT5520-K9-8-10-105-0.aes"),
            mock.call("transfer download start"),
        ]
    )
    device.native.send_command.assert_has_calls(
        [mock.call("y", expect_string="File transfer is successful.", delay_factor=3)]
    )
    assert file_copied is True


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
def test_file_copy_config(mock_convert_filename_to_version, aireos_send_command_timing, aireos_send_command):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    device = aireos_send_command_timing([""] * 8)
    aireos_send_command(["transfer_download_start_yes.txt"], device)
    device.file_copy("user", "pass", "10.1.1.1", "configs/host/latest.cfg", protocol="ftp", filetype="config")
    mock_convert_filename_to_version.assert_not_called()
    device.native.send_command_timing.assert_has_calls(
        [
            mock.call("transfer download datatype config"),
            mock.call("transfer download mode ftp"),
            mock.call("transfer download username user"),
            mock.call("transfer download password pass"),
            mock.call("transfer download serverip 10.1.1.1"),
            mock.call("transfer download path configs/host/"),
            mock.call("transfer download filename latest.cfg"),
            mock.call("transfer download start"),
        ]
    )
    device.native.send_command.assert_not_called()


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
def test_file_copy_no_copy(mock_convert_filename_to_version, aireos_device_path, aireos_send_command_timing):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    device = aireos_send_command_timing([""])
    with mock.patch(f"{aireos_device_path}.boot_options", new_callable=mock.PropertyMock) as mock_boot_optionsot:
        mock_boot_optionsot.return_value = {"primary": "8.10.105.0", "backup": "8.8.0.0", "sys": "8.10.105.0"}
        file_copied = device.file_copy("user", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")
        mock_boot_optionsot.assert_called()
    device.native.send_command_timing.assert_not_called()
    assert file_copied is False


@mock.patch("pyntc.devices.aireos_device.convert_filename_to_version")
def test_file_copy_error(mock_convert_filename_to_version, aireos_device_path, aireos_send_command_timing):
    mock_convert_filename_to_version.return_value = "8.10.105.0"
    device = aireos_send_command_timing(["send_command_error.txt"])
    with mock.patch(f"{aireos_device_path}.boot_options", new_callable=mock.PropertyMock) as mock_boot_optionsot:
        mock_boot_optionsot.return_value = {"primary": "8.8.105.0", "backup": "8.8.0.0", "sys": "8.8.105.0"}
        with pytest.raises(FileTransferError):
            device.file_copy("invalid", "pass", "10.1.1.1", "images/AIR-CT5520-K9-8-10-105-0.aes")


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os(
    mock_peer_redundancy_state,
    mock_wait,
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
    mock_reboot.assert_called_with(confirm=True, controller="both", save_config=True)
    mock_peer_redundancy_state.assert_called()
    mock_disable_wlans.assert_not_called()
    mock_enable_wlans.assert_not_called()


def test_install_os_no_install(aireos_image_booted, aireos_boot_image):
    device = aireos_image_booted([True])
    assert device.install_os(aireos_boot_image) is False
    device._image_booted.assert_called_once()


@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_error(
    mock_peer_redundancy_state, mock_wait, mock_reboot, mock_set_boot_options, aireos_image_booted, aireos_boot_image
):
    device = aireos_image_booted([False, False])
    with pytest.raises(OSInstallError) as boot_error:
        device.install_os(aireos_boot_image)
    assert boot_error.value.message == f"{device.host} was unable to boot into {aireos_boot_image}"
    device._image_booted.assert_has_calls([mock.call(aireos_boot_image)] * 2)


@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_error_peer(
    mock_peer_redundancy_state, mock_wait, mock_reboot, mock_set_boot_options, aireos_image_booted, aireos_boot_image
):
    mock_peer_redundancy_state.side_effect = ["standby hot", "unknown"]
    device = aireos_image_booted([False, True])
    with pytest.raises(OSInstallError) as boot_error:
        device.install_os(aireos_boot_image)
    assert boot_error.value.message == f"{device.host}-standby was unable to boot into {aireos_boot_image}"
    device._image_booted.assert_has_calls([mock.call(aireos_boot_image)] * 2)


@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_pass_controller(
    mock_peer_redundancy_state, mock_wait, mock_reboot, mock_set_boot_options, aireos_image_booted, aireos_boot_image
):
    device = aireos_image_booted([False, True])
    assert device.install_os(aireos_boot_image, controller="self", save_config=False) is True
    mock_reboot.assert_called_with(confirm=True, controller="self", save_config=False)


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_all_wlans(
    mock_peer_redundancy_state,
    mock_wait,
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
    mock_reboot.assert_called_with(confirm=True, controller="both", save_config=True)
    mock_peer_redundancy_state.assert_called()
    mock_disable_wlans.assert_called_with("all")
    mock_enable_wlans.assert_called_with("all")


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_select_wlans(
    mock_peer_redundancy_state,
    mock_wait,
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
    mock_reboot.assert_called_with(confirm=True, controller="both", save_config=True)
    mock_peer_redundancy_state.assert_called()
    mock_disable_wlans.assert_called_with([1, 3, 7])
    mock_enable_wlans.assert_called_with([1, 3, 7])


@mock.patch.object(AIREOSDevice, "enable_wlans")
@mock.patch.object(AIREOSDevice, "disable_wlans")
@mock.patch.object(AIREOSDevice, "set_boot_options")
@mock.patch.object(AIREOSDevice, "reboot")
@mock.patch.object(AIREOSDevice, "_wait_for_device_reboot")
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_wlans_error_disabling(
    mock_peer_redundancy_state,
    mock_wait,
    mock_reboot,
    mock_set_boot_options,
    mock_disable_wlans,
    mock_enable_wlans,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False])
    mock_disable_wlans.side_effect = [WLANDisableError(device.host, [1, 3, 7], [1, 3])]
    with pytest.raises(WLANDisableError):
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
@mock.patch.object(AIREOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
def test_install_os_disable_wlans_error_enabling(
    mock_peer_redundancy_state,
    mock_wait,
    mock_reboot,
    mock_set_boot_options,
    mock_disable_wlans,
    mock_enable_wlans,
    aireos_image_booted,
    aireos_boot_image,
):
    device = aireos_image_booted([False])
    mock_enable_wlans.side_effect = [WLANEnableError(device.host, [1, 3, 7], [1, 3])]
    with pytest.raises(WLANEnableError):
        device.install_os(aireos_boot_image, disable_wlans=[1, 3, 7])

    device._image_booted.assert_called_once()
    mock_set_boot_options.assert_called_once()
    mock_reboot.assert_called_once()
    mock_peer_redundancy_state.assert_called_once()


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
def test_open_prompt_found(mock_connect_handler, aireos_device):
    aireos_device.connected = True
    aireos_device.native.find_prompt.side_effect = [True]
    aireos_device.open()
    aireos_device.native.find_prompt.assert_called()
    mock_connect_handler.assert_not_called()
    assert aireos_device.connected is True


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
def test_open_prompt_not_found(mock_connect_handler, aireos_device, aireos_redundancy_state_path):
    aireos_device.connected = True
    aireos_device.native.find_prompt.side_effect = [Exception]
    with mock.patch(aireos_redundancy_state_path, new_callable=mock.PropertyMock) as redundnacy_state:
        redundnacy_state.return_value = True
        aireos_device.open()
    mock_connect_handler.assert_called()
    assert aireos_device.connected is True


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
def test_open_not_connected(mock_connect_handler, aireos_device, aireos_redundancy_state_path):
    aireos_device.connected = False
    with mock.patch(aireos_redundancy_state_path, new_callable=mock.PropertyMock) as redundnacy_state:
        redundnacy_state.return_value = True
        aireos_device.open()
    aireos_device.native.find_prompt.assert_not_called()
    mock_connect_handler.assert_called()
    assert aireos_device.connected is True


@mock.patch("pyntc.devices.aireos_device.ConnectHandler")
def test_open_standby(mock_connect_handler, aireos_device, aireos_redundancy_state_path):
    aireos_device.connected = False
    with mock.patch(aireos_redundancy_state_path, new_callable=mock.PropertyMock) as redundnacy_state:
        redundnacy_state.return_value = False
        aireos_device.open()
    aireos_device.native.find_prompt.assert_not_called()
    mock_connect_handler.assert_called()
    assert aireos_device.connected is False


def test_peer_redundancy_state_standby_hot(aireos_show):
    device = aireos_show(["show_redundancy_summary_sso_enabled.txt"])
    assert device.peer_redundancy_state == "standby hot"


def test_peer_redundancy_state_standalone(aireos_show):
    device = aireos_show(["show_redundancy_summary_standalone.txt"])
    assert device.peer_redundancy_state == "n/a"


@mock.patch("pyntc.devices.aireos_device.RebootSignal")
@mock.patch.object(AIREOSDevice, "save")
def test_reboot_confirm(mock_save, mock_reboot, aireos_send_command_timing, aireos_redundancy_mode_path):
    device = aireos_send_command_timing(["reset_system_confirm.txt", "reset_system_restart.txt"])
    with mock.patch(aireos_redundancy_mode_path, new_callable=mock.PropertyMock) as redundnacy_mode:
        redundnacy_mode.return_value = "sso enabled"
        device.reboot(confirm=True)
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
        device.reboot(confirm=True, timer="00:00:10", controller="both", save_config=False)
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
        device.reboot(confirm=True)
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
        device.reboot(confirm=True, timer="00:00:10", controller="both", save_config=False)
    device.native.send_command_timing.assert_has_calls(
        [mock.call("reset system in 00:00:10"), mock.call("n"), mock.call("y")]
    )
    mock_save.assert_not_called()


@mock.patch("pyntc.devices.aireos_device.RebootSignal")
def test_reboot_no_confirm(mock_reboot, aireos_device):
    aireos_device.reboot(confirm=False)
    aireos_device.native.send_command_timing.assert_not_called()


def test_redundancy_mode_sso(aireos_show):
    device = aireos_show(["show_redundancy_summary_sso_enabled.txt"])
    assert device.redundancy_mode == "sso enabled"


def test_redundancy_mode_standalone(aireos_show):
    device = aireos_show(["show_redundancy_summary_standalone.txt"])
    assert device.redundancy_mode == "sso disabled"


@mock.patch.object(AIREOSDevice, "open")
@mock.patch.object(AIREOSDevice, "show")
def test_redundancy_state_active(mock_show, mock_open, aireos_mock_path):
    device = AIREOSDevice("host", "user", "password")
    with open(f"{aireos_mock_path}/show_redundancy_summary_sso_enabled.txt") as fh:
        mock_show.return_value = fh.read()
    assert device.redundancy_state is True


@mock.patch.object(AIREOSDevice, "open")
@mock.patch.object(AIREOSDevice, "show")
def test_redundancy_state_standby(mock_show, mock_open, aireos_mock_path):
    device = AIREOSDevice("host", "user", "password")
    with open(f"{aireos_mock_path}/show_redundancy_summary_standby.txt") as fh:
        mock_show.return_value = fh.read()
    assert device.redundancy_state is False


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
        with pytest.raises(NTCFileNotFoundError) as fnfe:
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
        with pytest.raises(CommandError) as ce:
            aireos_device.set_boot_options(aireos_boot_image)
            assert ce.command == "boot primary"
    mock_config.assert_called()
    mock_save.assert_called()


@mock.patch.object(AIREOSDevice, "enable")
def test_show(mock_enable, aireos_send_command_timing):
    device = aireos_send_command_timing(["send_command_timing.txt"])
    data = device.show("send command timing")
    assert data.strip() == "This is only a test"
    mock_enable.assert_called()
    device.native.send_command_timing.assert_called()


@mock.patch.object(AIREOSDevice, "enable")
def test_show_expect(mock_enable, aireos_send_command):
    device = aireos_send_command(["send_command_expect.txt"])
    data = device.show("send command expect", expect_string="Continue?")
    assert data.strip() == "This is only a test\nContinue?"
    device.native.send_command.assert_called()


@mock.patch.object(AIREOSDevice, "enable")
def test_show_list(mock_enable, aireos_send_command_timing):
    device = aireos_send_command_timing(["send_command_timing.txt"] * 2)
    data = device.show_list(["send command timing"] * 2)
    clean_data = [result.strip() for result in data]
    assert clean_data == ["This is only a test"] * 2
    mock_enable.assert_called()
    device.native.send_command_timing.assert_has_calls([mock.call("send command timing")] * 2)


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
    with pytest.raises(FileTransferError) as fte:
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
    with pytest.raises(FileTransferError) as fte:
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
    with pytest.raises(FileTransferError) as fte:
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
