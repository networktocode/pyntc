from unittest import mock

import pytest

# from netmiko import ConnectHandler

from pyntc.devices.base_netmiko import BaseNetmikoDevice
from pyntc.devices import AIREOSDevice, ASADevice, IOSDevice


DEVICE_IDS = ("aireos", "asa", "ios")
# NETMIKO_MOCK = mock.Mock(ConnectHandler)
OPEN_METHOD = "open"
CONNECT_ARGS = {"host": "host", "username": "user", "password": "pass"}


def test_init():
    dev = BaseNetmikoDevice("host1", "user", "pass", "cisco_ios_ssh")
    assert dev.native is None
    assert dev.secret == ""
    assert dev.port == 22
    assert dev.connected is False


def test_connected_getter(netmiko_device):
    netmiko_device._connected = False
    assert netmiko_device.connected is False
    netmiko_device._connected = True
    assert netmiko_device.connected is True


def test_connected_setter(netmiko_device):
    netmiko_device._connected = False
    netmiko_device.connected = True
    assert netmiko_device._connected is True
    netmiko_device.connected = False
    assert netmiko_device.connected is False


# Test implementations of base class


@pytest.mark.parametrize(
    "device_implementation",
    (AIREOSDevice, ASADevice, IOSDevice),
    ids=DEVICE_IDS,
)
def test_connected_getter_implementations(device_implementation):
    with mock.patch.object(device_implementation, OPEN_METHOD):
        device = device_implementation(**CONNECT_ARGS)
        device._connected = False
        assert device.connected is False
        device._connected = True
        assert device.connected is True


@pytest.mark.parametrize(
    "device_implementation",
    (AIREOSDevice, ASADevice, IOSDevice),
    ids=DEVICE_IDS,
)
def test_connected_setter_implementations(device_implementation):
    with mock.patch.object(device_implementation, OPEN_METHOD):
        device = device_implementation(**CONNECT_ARGS)
        device._connected = False
        device.connected = True
        assert device.connected is True
        device.connected = False
        assert device.connected is False
