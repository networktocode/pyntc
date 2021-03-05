"""Module for using a Cisco IOSXE WLC device over SSH."""
from .ios_device import IOSDevice


class IOSXEWLCDevice(IOSDevice):
    """Cisco IOSXE WLC Device Implementation."""

    def show(self, command, expect_string=None, **netmiko_args):
        self.enable()
        return self._send_command(command, expect_string=expect_string, **netmiko_args)
