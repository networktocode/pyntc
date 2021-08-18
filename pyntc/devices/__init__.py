"""Device drivers."""

from .eos_device import EOSDevice
from .nxos_device import NXOSDevice
from .ios_device import IOSDevice
from .jnpr_device import JunosDevice
from .asa_device import ASADevice
from .f5_device import F5Device
from .aireos_device import AIREOSDevice
from .iosxewlc_device import IOSXEWLCDevice


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
