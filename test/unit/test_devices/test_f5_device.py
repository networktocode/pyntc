from unittest import mock

from pyntc.devices.f5_device import F5Device


@mock.patch("pyntc.devices.f5_device.bigsuds.BIGIP")
@mock.patch("pyntc.devices.f5_device.ManagementRoot")
def test_it_works(api, bigip):
    device = F5Device("test", "test", "test")

    obj = device.facts

    assert obj is not None
