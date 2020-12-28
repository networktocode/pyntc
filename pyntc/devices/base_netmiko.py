"""Module for netmiko base driver."""
from typing import Any  # , List, Union, Iterable, Callable, Mapping

# from netmiko import ConnectHandler

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
        self.device_type = device_type
        self.native = None
        self.secret = secret
        self.port = int(port)
        self._connected = False

        # Implement once open() method is implemented in base class.
        # self.open(confirm_active=confirm_active, **netmiko_args)

    # Properties

    @property
    def connected(self) -> bool:
        """
        The connection status of the device.

        Returns:
            bool: True if the device is connected, else False.
        """
        return self._connected

    @connected.setter
    def connected(self, value: bool) -> None:
        self._connected = value

    # Methods

    '''
    TODO: Build in all dependent methods/properties then uncomment
    def open(self, confirm_active: bool = True, **netmiko_args: Any) -> None:
        """
        Open a connection to the network device.

        This method will close the connection if ``confirm_active`` is True and the device is not active.
        Devices that do not have high availibility are considred active.

        Args:
            confirm_active (bool): Determines if device's high availability state should be validated before leaving connection open.
            **netmiko_args: Args to pass to Netmiko's ConnectHandler class.

        Raises:
            DeviceNotActiveError: When ``confirm_active`` is True, and the device high availabilit state is not active.
            TypeError: When **netmiko_args provides a value that is not part of ``netmiko.ConnectHandler`` calling signature.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.open()
            raised DeviceNotActiveError:
            host1 is not the active device.

            device state: standby hot
            peer state:   active

            >>> device.open(confirm_active=False)
            >>> device.connected
            True
            >>>
        """
        if self.connected:
            try:
                self.native.find_prompt()
            except Exception:
                self._connected = False

        if not self.connected:
            try:
                self.native = ConnectHandler(
                    device_type=self.device_type,
                    ip=self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    secret=self.secret,
                    verbose=False,
                    **netmiko_args,
                )
            except TypeError as err:
                raise TypeError(f"Netmiko Driver's {err.args[0]}")

            self._connected = True

        if confirm_active:
            self.confirm_is_active()
    '''
