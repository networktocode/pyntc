import mock
import pytest

from pyntc.devices import IOSXEWLCDevice
from pyntc.devices import iosxewlc_device as iosxewlc_module
from pyntc.errors import CommandError


@mock.patch.object(IOSXEWLCDevice, "open")
@mock.patch.object(IOSXEWLCDevice, "show")
def test_wait_for_device_reboot_returns(mock_show, mock_open, iosxewlc_device):
    timeout = 3
    iosxewlc_device._wait_for_device_reboot(timeout=timeout)
    mock_open.assert_called()
    mock_show.assert_called()


@mock.patch.object(IOSXEWLCDevice, "open")
@mock.patch.object(IOSXEWLCDevice, "show")
def test_wait_for_device_reboot_multiple_iterations(mock_show, mock_open, iosxewlc_device):
    timeout = 3
    mock_open.side_effect = [Exception("Cannot connect"), Exception("Cannot connect"), None]
    iosxewlc_device._wait_for_device_reboot(timeout=timeout)
    assert 3 == mock_open.call_count


@mock.patch.object(IOSXEWLCDevice, "hostname", new_callable=mock.PropertyMock)
@mock.patch.object(IOSXEWLCDevice, "open")
@mock.patch.object(IOSXEWLCDevice, "show")
def test_wait_for_device_reboot_timeout(mock_show, mock_open, mock_hostname, iosxewlc_device):
    timeout = 3
    mock_hostname.return_value = "ntc-iosxewlc-01"
    mock_open.side_effect = [Exception("Cannot connect")]
    with pytest.raises(iosxewlc_module.RebootTimeoutError) as err:
        iosxewlc_device._wait_for_device_reboot(timeout=timeout)

    assert err.value.message == "Unable to reconnect to ntc-iosxewlc-01 after 3 seconds"
    assert mock_open.call_count > 3


@mock.patch.object(IOSXEWLCDevice, "open")
@mock.patch.object(IOSXEWLCDevice, "show")
def test_wait_for_device_start_reboot_returns(mock_show, mock_open, iosxewlc_device):
    timeout = 3
    mock_open.side_effect = [Exception("Can't connect")]
    mock_show.side_effect = [CommandError("show version", "Error in performing command")]
    iosxewlc_device._wait_for_device_start_reboot(timeout=timeout)


@mock.patch.object(IOSXEWLCDevice, "open")
@mock.patch.object(IOSXEWLCDevice, "show")
def test_wait_for_device_start_reboot_multiple_iterations(mock_show, mock_open, iosxewlc_device):
    timeout = 3
    mock_open.side_effect = [None, None, Exception("Can't connect")]
    iosxewlc_device._wait_for_device_start_reboot(timeout=timeout)
    assert 3 == mock_open.call_count


@mock.patch.object(IOSXEWLCDevice, "hostname", new_callable=mock.PropertyMock)
@mock.patch.object(IOSXEWLCDevice, "open")
@mock.patch.object(IOSXEWLCDevice, "show")
def test_wait_for_device_start_reboot_timeout(mock_show, mock_open, mock_hostname, iosxewlc_device):
    timeout = 3
    mock_hostname.return_value = "ntc-iosxewlc-01"
    with pytest.raises(iosxewlc_module.WaitingRebootTimeoutError) as err:
        iosxewlc_device._wait_for_device_start_reboot(timeout=timeout)

    assert (
        err.value.message == "ntc-iosxewlc-01 has not rebooted in 3 seconds after issuing install mode upgrade command"
    )
    assert mock_open.call_count > 3
    assert mock_show.call_count > 3


def test_show(iosxewlc_send_command):
    command = "show_ip_arp"
    device = iosxewlc_send_command([f"{command}.txt"])
    device.show(command)
    device._send_command.assert_called_with("show_ip_arp", expect_string=None)
    device._send_command.assert_called_once()


def test_show_delay_factor(iosxewlc_send_command):
    command = "show_ip_arp"
    delay_factor = 20
    device = iosxewlc_send_command([f"{command}"])
    device.show(command, delay_factor=delay_factor)
    device._send_command.assert_called_with("show_ip_arp", expect_string=None, delay_factor=delay_factor)
    device._send_command.assert_called_once()


# Test install mode upgrade
@mock.patch.object(IOSXEWLCDevice, "_image_booted")
@mock.patch.object(IOSXEWLCDevice, "set_boot_options")
@mock.patch.object(IOSXEWLCDevice, "show")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_start_reboot")
@mock.patch.object(IOSXEWLCDevice, "_get_file_system")
@mock.patch.object(IOSXEWLCDevice, "fast_cli", new_callable=mock.PropertyMock)
def test_install_os_install_mode(
    mock_fast_cli,
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
    actual = iosxewlc_device.install_os(image_name)

    # Test the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"install add file {file_system}{image_name} activate commit prompt-level none", delay_factor=20
    )
    assert 2 == mock_image_booted.call_count
    assert 3 == mock_fast_cli.call_count
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
@mock.patch.object(IOSXEWLCDevice, "fast_cli", new_callable=mock.PropertyMock)
def test_install_os_install_mode_failed(
    mock_fast_cli,
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
        iosxewlc_device.install_os(image_name)

    assert err.value.message == "ntc-iosxewlc-01 was unable to boot into C9800-40-universalk9_wlc.16.12.05.SPA.bin"

    # Check the results
    mock_set_boot_options.assert_called_with("packages.conf")
    mock_show.assert_called_with(
        f"install add file {file_system}{image_name} activate commit prompt-level none", delay_factor=20
    )
    assert 2 == mock_image_booted.call_count
    assert 3 == mock_fast_cli.call_count
    mock_wait_for_reboot.assert_called()
    mock_wait_for_reboot_start.assert_called()


# Test install mode upgrade not needed
@mock.patch.object(IOSXEWLCDevice, "_image_booted")
@mock.patch.object(IOSXEWLCDevice, "set_boot_options")
@mock.patch.object(IOSXEWLCDevice, "show")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_reboot")
@mock.patch.object(IOSXEWLCDevice, "_wait_for_device_start_reboot")
@mock.patch.object(IOSXEWLCDevice, "_get_file_system")
@mock.patch.object(IOSXEWLCDevice, "hostname", new_callable=mock.PropertyMock)
@mock.patch.object(IOSXEWLCDevice, "fast_cli", new_callable=mock.PropertyMock)
def test_install_os_already_installed(
    mock_fast_cli,
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
    mock_image_booted.side_effect = [True, False]
    mock_show.side_effect = [IOError("Search pattern never detected in send_command")]
    # Call the install os function
    actual = iosxewlc_device.install_os(image_name)

    # Check the results
    mock_fast_cli.assert_not_called()
    mock_set_boot_options.assert_not_called()
    mock_show.assert_not_called()
    mock_image_booted.assert_called()
    assert actual is False
