from pyntc.devices.base_netmiko import BaseNetmikoDevice
# from pyntc.devices import AIREOSDevice, ASADevice, IOSDevice


def test_init():
    dev = BaseNetmikoDevice("host1", "user", "pass", "cisco_ios_ssh")
    assert dev.native is None
    assert dev.secret == ""
    assert dev.port == 22
    assert dev._connected is False
