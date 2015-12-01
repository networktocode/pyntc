from .devices.eos_device import EOSDevice
from .devices.nxos_device import NXOSDevice

from .errors import UnsupportedDeviceError

def get_device(vendor, *args, **kwargs):
    device_map = {
        'nxos': NXOSDevice,
        'eos': EOSDevice,
    }
    try:
        device_class = device_map[vendor.lower()]
        return device_class(*args, **kwargs)
    except KeyError:
        raise UnsupportedDeviceError(vendor)