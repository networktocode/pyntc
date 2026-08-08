import os
import sys

import mock
import pytest

from pyntc import ntc_device, ntc_device_by_name
from pyntc.devices import EOSDevice, EOSSSHDevice, IOSDevice, NXOSDevice, supported_devices
from pyntc.errors import ConfFileNotFoundError, UnsupportedDeviceError

BAD_DEVICE_TYPE = "238nzsvkn3981"
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


@mock.patch("pyntc.devices.aireos_device.AIREOSDevice.open")
@mock.patch("pyntc.devices.f5_device.ManagementRoot", create=True)
@mock.patch("pyntc.devices.asa_device.ASADevice.open")
@mock.patch("pyntc.devices.ios_device.IOSDevice.open")
@mock.patch("pyntc.devices.iosxr_device.IOSXRDevice.open")
@mock.patch("pyntc.devices.nxos_device.NXOSDevice.open")
@mock.patch("pyntc.devices.eos_ssh_device.EOSSSHDevice.open")
@mock.patch("pyntc.devices.jnpr_device.JunosNativeSW")
@mock.patch("pyntc.devices.jnpr_device.JunosNativeDevice.open")
@mock.patch("pyntc.devices.jnpr_device.JunosNativeDevice.timeout")
@pytest.mark.parametrize("device_type,expected", supported_devices.items(), ids=list(supported_devices))
def test_device_creation(
    j_timeout, j_open, j_nsw, eos_ssh_open, nx_open, xr_open, i_open, a_open, f_mr, air_open, device_type, expected
):
    # Skip f5 on python >3.11
    if sys.version_info >= (3, 12) and device_type == "f5_tmos_icontrol":
        pytest.skip(f"F5 not supported in Python {sys.version}")
    device = ntc_device(device_type, "host", "user", "pass")
    assert isinstance(device, expected)


def test_unsupported_device():
    with pytest.raises(UnsupportedDeviceError):
        ntc_device(BAD_DEVICE_TYPE)


@mock.patch("pyntc.devices.ios_device.IOSDevice.open")
@mock.patch("pyntc.devices.nxos_device.NXOSDevice.open")
@mock.patch("pyntc.devices.eos_ssh_device.EOSSSHDevice.open")
@mock.patch("pyntc.devices.jnpr_device.JunosDevice.open")
def test_device_by_name(j_open, eos_ssh_open, nx_open, i_open):
    config_filepath = os.path.join(FIXTURES_DIR, ".ntc.conf.sample")

    nxos_device = ntc_device_by_name("test_nxos", filename=config_filepath)
    assert isinstance(nxos_device, NXOSDevice)

    eos_device = ntc_device_by_name("test_eos", filename=config_filepath)
    assert isinstance(eos_device, EOSDevice)

    eos_ssh_device = ntc_device_by_name("test_eos_ssh", filename=config_filepath)
    assert isinstance(eos_ssh_device, EOSSSHDevice)

    ios_device = ntc_device_by_name("test_ios", filename=config_filepath)
    assert isinstance(ios_device, IOSDevice)


def test_no_conf_file():
    with pytest.raises(ConfFileNotFoundError):
        ntc_device_by_name("test_bad_device", filename="/bad/file/path")
