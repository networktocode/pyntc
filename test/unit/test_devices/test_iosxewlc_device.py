import mock
import pytest

from pyntc.devices import IOSXEWLCDevice
from pyntc.devices import iosxewlc_device as iosxewlc_module


def test_show(iosxewlc_send_command):
    command = "show_ip_arp"
    device = iosxewlc_send_command([f"{command}.txt"])
    device.show(command)
    device.native.send_command.assert_called_with(command_string="show_ip_arp")
    device.native.send_command.assert_called_once()


def test_show_delay_factor(iosxewlc_send_command):
    command = "show_ip_arp"
    delay_factor = 20
    device = iosxewlc_send_command([f"{command}"])
    device.show(command, delay_factor=delay_factor)
    device.native.send_command.assert_called_with(command_string="show_ip_arp", delay_factor=delay_factor)
    device.native.send_command.assert_called_once()


# Test install mode upgrade
@mock.patch.object(IOSXEWLCDevice, "_image_booted")
@mock.patch.object(IOSXEWLCDevice, "set_boot_options")
@mock.patch.object(IOSXEWLCDevice, "show")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_start_reboot")
@mock.patch.object(IOSXEWLCDevice, "_get_file_system")
def test_install_os_install_mode(
    mock_get_file_system,
    mock_wait_for_reboot_start,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    iosxewlc_device,
):
    image_name = "C9800-40-universalk9_wlc.16.12.05.SPA.bin"
    file_system = "bootflash:"
    mock_get_file_system.return_value = file_system
    mock_image_booted.side_effect = [False, True]
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install_os
    actual = iosxewlc_device.install_os(image_name, install_mode=True)

    # Test the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"install add file {file_system}{image_name} activate commit prompt-level none", delay_factor=20
    )
    mock_image_booted.assert_called()
    mock_wait_for_reboot.assert_called()
    mock_wait_for_reboot_start.assert_called()
    assert actual is True


# Test install mode upgrade fail
@mock.patch.object(IOSXEWLCDevice, "_image_booted")
@mock.patch.object(IOSXEWLCDevice, "set_boot_options")
@mock.patch.object(IOSXEWLCDevice, "show")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_start_reboot")
@mock.patch.object(IOSXEWLCDevice, "_get_file_system")
@mock.patch.object(IOSXEWLCDevice, "hostname", new_callable=mock.PropertyMock)
def test_install_os_install_mode_failed(
    mock_hostname,
    mock_get_file_system,
    mock_wait_for_reboot_start,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    iosxewlc_device,
):
    mock_hostname.return_value = "ntc-iosxewlc-01"
    image_name = "C9800-40-universalk9_wlc.16.12.05.SPA.bin"
    file_system = "bootflash:"
    mock_get_file_system.return_value = file_system
    mock_image_booted.side_effect = [False, False]
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install os function
    with pytest.raises(iosxewlc_module.OSInstallError) as err:
        iosxewlc_device.install_os(image_name, install_mode=True)

    assert err.value.message == "ntc-iosxewlc-01 was unable to boot into C9800-40-universalk9_wlc.16.12.05.SPA.bin"

    # Check the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"install add file {file_system}{image_name} activate commit prompt-level none", delay_factor=20
    )
    mock_image_booted.assert_called()
    mock_wait_for_reboot.assert_called()
    mock_wait_for_reboot_start.assert_called()


# Test install mode set to False
@mock.patch.object(IOSXEWLCDevice, "_image_booted")
@mock.patch.object(IOSXEWLCDevice, "set_boot_options")
@mock.patch.object(IOSXEWLCDevice, "show")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_start_reboot")
@mock.patch.object(IOSXEWLCDevice, "_get_file_system")
@mock.patch.object(IOSXEWLCDevice, "hostname", new_callable=mock.PropertyMock)
def test_install_os_install_mode_false(
    mock_hostname,
    mock_get_file_system,
    mock_wait_for_reboot_start,
    mock_wait_for_reboot,
    mock_show,
    mock_set_boot_options,
    mock_image_booted,
    iosxewlc_device,
):
    mock_hostname.return_value = "ntc-iosxewlc-01"
    image_name = "C9800-40-universalk9_wlc.16.12.05.SPA.bin"
    file_system = "bootflash:"
    mock_get_file_system.return_value = file_system
    mock_image_booted.side_effect = [False, False]
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install os function
    with pytest.raises(iosxewlc_module.InstallModeRequired) as err:
        iosxewlc_device.install_os(image_name, install_mode=False)

    assert err.value.message == "Only install mode is supported on IOSXE WLC devices."

    # Check the results
    mock_image_booted.assert_called()
    mock_set_boot_options.assert_not_called()
    mock_show.assert_not_called()
    mock_wait_for_reboot.assert_not_called()
    mock_wait_for_reboot_start.assert_not_called()
