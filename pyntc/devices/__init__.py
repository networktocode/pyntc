"""Supported devices are stored here. Every supported device needs a
device_type stored as a string, and a class subclassed from BaseDevice.
"""

from .eos_device import EOSDevice, EOS_API_DEVICE_TYPE
from .nxos_device import NXOSDevice, NXOS_API_DEVICE_TYPE
from .ios_device import IOSDevice, IOS_SSH_DEVICE_TYPE
from .jnpr_device import JunosDevice, JNPR_DEVICE_TYPE
from .base_device import BaseDevice


supported_devices = {
    EOS_API_DEVICE_TYPE: EOSDevice,
    NXOS_API_DEVICE_TYPE: NXOSDevice,
    IOS_SSH_DEVICE_TYPE: IOSDevice,
    JNPR_DEVICE_TYPE: JunosDevice,
}
