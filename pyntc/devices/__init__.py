"""Supported devices are stored here. Every supported device needs a
device_type stored as a string, and a class subclassed from BaseDevice.
"""

from .eos_device import EOSDevice
from .nxos_device import NXOSDevice
from .ios_device import IOSDevice
from .jnpr_device import JunosDevice
from .asa_device import ASADevice
from .f5_device import F5Device
from .aireos_device import AIREOSDevice


supported_devices = {
    "cisco_asa_ssh": ASADevice,
    "arista_eos_eapi": EOSDevice,
    "f5_tmos_icontrol": F5Device,
    "cisco_ios_ssh": IOSDevice,
    "juniper_junos_netconf": JunosDevice,
    "cisco_nxos_nxapi": NXOSDevice,
    "cisco_aireos_ssh": AIREOSDevice,
}
