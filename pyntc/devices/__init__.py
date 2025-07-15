"""Device drivers."""

from .aireos_device import AIREOSDevice
from .asa_device import ASADevice
from .eos_device import EOSDevice
from .f5_device import F5Device
from .ios_device import IOSDevice
from .iosxewlc_device import IOSXEWLCDevice
from .jnpr_device import JunosDevice
from .nxos_device import NXOSDevice

supported_devices = {
    "cisco_asa_ssh": ASADevice,
    "arista_eos_eapi": EOSDevice,
    "f5_tmos_icontrol": F5Device,
    "cisco_ios_ssh": IOSDevice,
    "juniper_junos_netconf": JunosDevice,
    "cisco_nxos_nxapi": NXOSDevice,
    "cisco_aireos_ssh": AIREOSDevice,
    "cisco_iosxewlc_ssh": IOSXEWLCDevice,
}
