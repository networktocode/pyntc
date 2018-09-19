"""Supported devices are stored here. Every supported device needs a
device_type stored as a string, and a class subclassed from BaseDevice.
"""

from .eos_device import EOSDevice, EOS_API_DEVICE_TYPE
from .nxos_device import NXOSDevice, NXOS_API_DEVICE_TYPE
from .ios_device import IOSDevice, IOS_SSH_DEVICE_TYPE
from .jnpr_device import JunosDevice, JNPR_DEVICE_TYPE
from .asa_device import ASADevice, ASA_SSH_DEVICE_TYPE
from .f5_device import F5Device, F5_API_DEVICE_TYPE
from .base_device import BaseDevice


DEVICE_CLASS_KEY = 'device_class'


supported_devices = {
    EOS_API_DEVICE_TYPE: {
        DEVICE_CLASS_KEY: EOSDevice,
    },

    NXOS_API_DEVICE_TYPE: {
        DEVICE_CLASS_KEY: NXOSDevice,
    },

    IOS_SSH_DEVICE_TYPE: {
        DEVICE_CLASS_KEY: IOSDevice
    },

    JNPR_DEVICE_TYPE: {
        DEVICE_CLASS_KEY: JunosDevice,
    },

    ASA_SSH_DEVICE_TYPE: {
        DEVICE_CLASS_KEY: ASADevice,
    },

    F5_API_DEVICE_TYPE: {
        DEVICE_CLASS_KEY: F5Device,
    },
}
