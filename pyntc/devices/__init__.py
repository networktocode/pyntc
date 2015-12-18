from .eos_device import EOSDevice
from .nxos_device import NXOSDevice
from .base_device import BaseDevice


DEVICE_CLASS_KEY = 'device_class'

supported_devices = {
    'eos': {
        DEVICE_CLASS_KEY: EOSDevice,
    },

    'nxos': {
        DEVICE_CLASS_KEY: NXOSDevice,
    }
}