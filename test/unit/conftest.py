import os
from unittest import mock

import pytest
from netmiko.cisco import CiscoWlcSSH, CiscoAsaSSH, CiscoIosSSH

from pyntc.devices.base_netmiko import BaseNetmikoDevice
from pyntc.devices import AIREOSDevice, ASADevice, IOSDevice


NETMIKO_CLASS_MAP = {
    AIREOSDevice: CiscoWlcSSH,
    ASADevice: CiscoAsaSSH,
    IOSDevice: CiscoIosSSH,
}


def get_side_effects(mock_path, side_effects):
    effects = []
    for effect in side_effects:
        if isinstance(effect, str) and os.path.isfile(f"{mock_path}/{effect}"):
            with open(f"{mock_path}/{effect}") as fh:
                effects.append(fh.read())
        else:
            effects.append(effect)
    return effects


@pytest.fixture
def aireos_boot_image():
    return "8.2.170.0"


@pytest.fixture
def aireos_boot_path(aireos_device_path):
    return f"{aireos_device_path}.boot_options"


@pytest.fixture
def aireos_config(aireos_device, aireos_mock_path):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_config_set.side_effect = get_side_effects(aireos_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def aireos_device():
    with mock.patch.object(AIREOSDevice, "confirm_is_active") as mock_confirm:
        mock_confirm.return_value = True
        with mock.patch("pyntc.devices.aireos_device.ConnectHandler") as ch:
            device = AIREOSDevice("host", "user", "password")
            device.native = ch
            yield device


@pytest.fixture
def aireos_device_path():
    return "pyntc.devices.aireos_device.AIREOSDevice"


@pytest.fixture
def aireos_expected_wlans():
    return {
        5: {
            "profile": "guest_cppm",
            "ssid": "guest_cppm",
            "status": "Enabled",
            "interface": "management",
        },
        15: {
            "profile": "Smartphone_xx",
            "ssid": "TestInternet;WLANXX",
            "status": "Enabled",
            "interface": "management",
        },
        16: {
            "profile": "Test1_WIGA",
            "ssid": "testguest",
            "status": "Disabled",
            "interface": "management",
        },
        20: {
            "profile": "Campus;WLAN-002",
            "ssid": "TestCampus;WLAN-002",
            "status": "Enabled",
            "interface": "wireless client 104",
        },
        21: {
            "profile": "testpoc",
            "ssid": "testpoc",
            "status": "Disabled",
            "interface": "management",
        },
        22: {
            "profile": "TestNewAirway",
            "ssid": "TestNewAirway",
            "status": "Enabled",
            "interface": "rcn",
        },
        24: {
            "profile": "TestAirway",
            "ssid": "TestAirway",
            "status": "Disabled",
            "interface": "wireless client 102",
        },
    }


@pytest.fixture
def aireos_image_booted(aireos_device_path, aireos_device):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        with mock.patch.object(AIREOSDevice, "_image_booted") as mock_ib:
            mock_ib.side_effect = get_side_effects(aireos_device_path, side_effects)
            device._image_booted = mock_ib
        return device

    return _mock


@pytest.fixture
def aireos_mock_path(mock_path):
    return f"{mock_path}/aireos"


@pytest.fixture
def aireos_redundancy_mode_path(aireos_device_path):
    return f"{aireos_device_path}.redundancy_mode"


@pytest.fixture
def aireos_send_command(aireos_device, aireos_mock_path):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command.side_effect = get_side_effects(aireos_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def aireos_send_command_timing(aireos_device, aireos_mock_path):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command_timing.side_effect = get_side_effects(aireos_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def aireos_show(aireos_device, aireos_mock_path):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        with mock.patch.object(AIREOSDevice, "show") as mock_show:
            mock_show.side_effect = get_side_effects(aireos_mock_path, side_effects)
        device.show = mock_show
        return device

    return _mock


@pytest.fixture
def aireos_show_list(aireos_device, aireos_mock_path):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        with mock.patch.object(AIREOSDevice, "show_list") as mock_show_list:
            mock_show_list.side_effect = get_side_effects(aireos_mock_path, side_effects)
        device.show_list = mock_show_list
        return device

    return _mock


@pytest.fixture
def mock_path():
    filepath = os.path.abspath(__file__)
    dirpath = os.path.dirname(filepath)
    return f"{dirpath}/test_devices/device_mocks"


@pytest.fixture
def asa_device():
    with mock.patch("pyntc.devices.asa_device.ConnectHandler") as ch:
        device = ASADevice("host", "user", "password")
        device.native = ch
        yield device


@pytest.fixture
def asa_mock_path(mock_path):
    return f"{mock_path}/asa"


@pytest.fixture
def asa_send_command(asa_device, asa_mock_path):
    def _mock(side_effects, existing_device=None, device=asa_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command.side_effect = get_side_effects(asa_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def asa_send_command_timing(asa_device, asa_mock_path):
    def _mock(side_effects, existing_device=None, device=asa_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command_timing.side_effect = get_side_effects(asa_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def ios_config(ios_device, ios_mock_path):
    def _mock(side_effects, existing_device=None, device=ios_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_config_set.side_effect = get_side_effects(ios_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def ios_device():
    with mock.patch.object(IOSDevice, "confirm_is_active") as mock_confirm:
        mock_confirm.return_value = True
        with mock.patch("pyntc.devices.ios_device.ConnectHandler") as ch:
            device = IOSDevice("host", "user", "password")
            device.native = ch
            yield device


@pytest.fixture
def ios_mock_path(mock_path):
    return f"{mock_path}/ios"


@pytest.fixture
def ios_redundancy_info():
    return (
        "       Available system uptime = 5 weeks, 3 days, 15 hours, 8 minutes\n"
        "Switchovers system experienced = 0\n"
        "              Standby failures = 0\n"
        "        Last switchover reason = none\n"
        "\n"
        "                 Hardware Mode = Duplex\n"
        "    Configured Redundancy Mode = Stateful Switchover\n"
        "     Operating Redundancy Mode = Stateful Switchover\n"
        "              Maintenance Mode = Disabled\n"
        "                Communications = Up\n"
        "          "
    )


@pytest.fixture
def ios_redundancy_other():
    return (
        "              Standby Location = slot 2/1\n"
        "        Current Software state = STANDBY HOT\n"
        "       Uptime in current state = 5 weeks, 3 days, 14 hours, 35 minutes\n"
        "                 Image Version = Cisco IOS Software, IOS-XE Software, Catalyst 4500 L3 Switch  Software (cat4500e-UNIVERSALK9-M), Version 03.10.03.E RELEASE SOFTWARE (fc3)\n"
        "Technical Support: http://www.cisco.com/techsupport\n"
        "Copyright (c) 1986-2019 by Cisco Systems, Inc.\n"
        "Compiled Mon 15-Jul-19 08:51 by pr\n"
        "               BOOT = bootflash:/cat4500e-universalk9.SPA.03.10.03.E.152-6.E3.bin,12;bootflash:/cat4500e-universalk9.SPA.03.08.08.E.152-4.E8.bin,12;\n"
        "        Configuration register = 0x2102\n"
    )


@pytest.fixture
def ios_redundancy_self():
    return (
        "               Active Location = slot 1/1\n"
        "        Current Software state = ACTIVE\n"
        "       Uptime in current state = 5 weeks, 3 days, 15 hours, 4 minutes\n"
        "                 Image Version = Cisco IOS Software, IOS-XE Software, Catalyst 4500 L3 Switch  Software (cat4500e-UNIVERSALK9-M), Version 03.10.03.E RELEASE SOFTWARE (fc3)\n"
        "Technical Support: http://www.cisco.com/techsupport\n"
        "Copyright (c) 1986-2019 by Cisco Systems, Inc.\n"
        "Compiled Mon 15-Jul-19 08:51 by prod\n"
        "               BOOT = bootflash:/cat4500e-universalk9.SPA.03.10.03.E.152-6.E3.bin,12;bootflash:/cat4500e-universalk9.SPA.03.08.08.E.152-4.E8.bin,12;\n"
        "        Configuration register = 0x2102\n"
    )


@pytest.fixture
def ios_send_command(ios_device, ios_mock_path):
    def _mock(side_effects, existing_device=None, device=ios_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command.side_effect = get_side_effects(ios_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def ios_send_command_timing(ios_device, ios_mock_path):
    def _mock(side_effects, existing_device=None, device=ios_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command_timing.side_effect = get_side_effects(ios_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def ios_show(ios_device, ios_mock_path):
    def _mock(side_effects, existing_device=None, device=ios_device):
        if existing_device is not None:
            device = existing_device
        with mock.patch.object(IOSDevice, "show") as mock_show:
            mock_show.side_effect = get_side_effects(ios_mock_path, side_effects)
        device.show = mock_show
        return device

    return _mock


@pytest.fixture
def netmiko_device():
    # with mock.patch.object(BaseNetmikoDevice, "confirm_is_active") as mock_confirm:
    #     mock_confirm.return_value = True
    with mock.patch("netmiko.base_connection.BaseConnection", autospec=True) as base_connection:
        with mock.patch.object(BaseNetmikoDevice, "__init__", return_value=None):
            device = BaseNetmikoDevice()
            device.native = base_connection
        return device


@pytest.fixture
def netmiko_command(netmiko_device, netmiko_mock_path):
    def _mock(netmiko_method, side_effects, existing_device=None, device=netmiko_device):
        if existing_device is not None:
            device = existing_device
        side_effects = get_side_effects(netmiko_mock_path, side_effects)
        native_method = getattr(device.native, netmiko_method)
        native_method.side_effect = side_effects
        return device

    return _mock


@pytest.fixture
def netmiko_mock_path(mock_path):
    return f"{mock_path}/netmiko"


@pytest.fixture
def netmiko_send_commands(netmiko_device, netmiko_mock_path):
    def _mock(side_effects, existing_device=None, device=netmiko_device):
        if existing_device is not None:
            device = existing_device
        with mock.patch.object(device, "_send_commands", autospec=True) as mock_send_commands:
            mock_send_commands.side_effect = get_side_effects(netmiko_mock_path, side_effects)
        device._send_commands = mock_send_commands
        return device

    return _mock


@pytest.fixture
def netmiko_show(netmiko_device, netmiko_mock_path):
    def _mock(side_effects, existing_device=None, device=netmiko_device):
        if existing_device is not None:
            device = existing_device
        with mock.patch.object(device, "show", autospec=True) as mock_show:
            mock_show.side_effect = get_side_effects(netmiko_mock_path, side_effects)
        device.show = mock_show
        return device

    return _mock


@pytest.fixture()
def mock_implementation_show():
    def _mock(implementation, side_effects):
        device = implementation()
        with mock.patch.object(device, "show", autospec=True) as mock_show:
            mock_show.side_effect = side_effects
        device.show = mock_show
        return device

    return _mock


@pytest.fixture
def netmiko_base_implementation(request):
    pyntc_class = request.param
    original_init = pyntc_class.__init__
    pyntc_class.__init__ = mock.Mock(spec=original_init, return_value=None)
    pyntc_class.native = mock.Mock(NETMIKO_CLASS_MAP[pyntc_class])
    yield pyntc_class
    pyntc_class.__init__ = original_init


def pytest_generate_tests(metafunc):
    if "netmiko_method" in metafunc.fixturenames:
        metafunc.parametrize(
            "netmiko_method",
            ("send_command", "send_command_timing", "send_config_set"),
            ids=["command", "timing", "config"],
        )
