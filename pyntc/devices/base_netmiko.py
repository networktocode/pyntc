"""Module for netmiko base driver."""
from typing import Any  # , List, Union, Iterable, Callable, Mapping

from .base_device import BaseDevice, fix_docs
# from pyntc.errors import CommandError, CommandListError


@fix_docs
class BaseNetmikoDevice(BaseDevice):
    """Netmiko Base Driver."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        device_type: str,
        secret: str = "",
        port: int = 22,
        **netmiko_args: Any,
    ) -> None:
        """
        Implementation of Devices that use Netmiko for connection driver.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            device_type (str): The device type per ``pyntc.devices.supported_devices``.
            secret (str): The password to escalate privilege on the device.
            port (int): The port to use to establish the connection.

        Example:
            >>> device = NetmikoBaseDevice(host="10.1.1.1", username="user", password="pass", device_type="cisco_ios_ssh")
            >>> device.show("show hostname")
            'ios-host'
            >>>

        TODO:
            Add confirm_active to call signature once open method is defined.
        """
        super().__init__(host, username, password, device_type=device_type)
        self.native = None
        self.secret = secret
        self.port = int(port)
        self._connected = False

        # Implement once open() method is implemented in base class.
        # self.open(confirm_active=confirm_active, **netmiko_args)
