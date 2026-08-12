"""Device drivers."""

from .aireos_device import AIREOSDevice
from .asa_device import ASADevice
from .eos_device import EOSDevice
from .eos_ssh_device import EOSSSHDevice
from .f5_device import F5Device
from .ios_device import IOSDevice
from .iosxewlc_device import IOSXEWLCDevice
from .iosxr_device import IOSXRDevice
from .jnpr_device import JunosDevice
from .nxos_device import NXOSDevice

supported_devices = {
    "cisco_asa_ssh": ASADevice,
    "arista_eos_eapi": EOSDevice,
    "arista_eos_ssh": EOSSSHDevice,
    "f5_tmos_icontrol": F5Device,
    "cisco_ios_ssh": IOSDevice,
    "cisco_iosxr_ssh": IOSXRDevice,
    "juniper_junos_netconf": JunosDevice,
    "cisco_nxos_nxapi": NXOSDevice,
    "cisco_aireos_ssh": AIREOSDevice,
    "cisco_iosxewlc_ssh": IOSXEWLCDevice,
}
