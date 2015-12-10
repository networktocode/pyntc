from .eos_device import EOSDevice
from .nxos_device import NXOSDevice


VENDOR_KEY = 'vendor'
DEVICE_CLASS_KEY = 'device_class'

supported_devices = {
    'eos': {
        VENDOR_KEY: 'Arista',
        DEVICE_CLASS_KEY: EOSDevice,
    },

    'nxos': {
        VENDOR_KEY: 'Cisco',
        DEVICE_CLASS_KEY: NXOSDevice,
    }
}