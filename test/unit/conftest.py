import os

import pytest
from unittest import mock

from pyntc.devices import AIREOSDevice


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
def aireos_device(aireos_redundancy_state):
    with mock.patch("pyntc.devices.aireos_device.ConnectHandler") as ch:
        device = AIREOSDevice("host", "user", "password")
        device.native = ch
        yield device


@pytest.fixture
def aireos_device_path():
    return "pyntc.devices.aireos_device.AIREOSDevice"


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
def aireos_redundancy_state(aireos_redundancy_state_path):
    with mock.patch(aireos_redundancy_state_path, new_callable=mock.PropertyMock) as rs:
        rs.return_value = True
        yield rs


@pytest.fixture
def aireos_redundancy_state_path(aireos_device_path):
    return f"{aireos_device_path}.redundancy_state"


@pytest.fixture
def aireos_send_command(aireos_device, aireos_mock_path):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command.side_effect = get_side_effects(aireos_mock_path, side_effects)
        return device

    return _mock


@pytest.fixture
def aireos_send_command_expect(aireos_device, aireos_mock_path):
    def _mock(side_effects, existing_device=None, device=aireos_device):
        if existing_device is not None:
            device = existing_device
        device.native.send_command_expect.side_effect = get_side_effects(aireos_mock_path, side_effects)
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
        device.show = mock_show_list
        return device

    return _mock


@pytest.fixture
def mock_path():
    filepath = os.path.abspath(__file__)
    dirpath = os.path.dirname(filepath)
    return f"{dirpath}/test_devices/device_mocks"
