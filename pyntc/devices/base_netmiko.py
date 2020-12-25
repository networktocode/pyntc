"""Module for netmiko base driver."""
import warnings
from typing import Any, Iterable, List, Union, Callable, Mapping

# from netmiko import ConnectHandler

from .base_device import BaseDevice, fix_docs
from ..errors import CommandError, CommandListError


@fix_docs
class BaseNetmikoDevice(BaseDevice):
    """Netmiko Base Driver."""

    error_keywords = ["% ", "Error:", "Incorrect usage"]

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

    def _check_command_output_has_error(self, command_response: str) -> bool:
        """
        Check response from device to see if an error was reported.

        Args:
            command_response (str): The response from sending a command to the device.

        Returns:
            bool: True when an error is detected in ``command_response``, else False.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> command_response = "output from show version"
            >>> device._check_command_output_has_error(command_response)
            >>> command_response = "% Error: invalid command"
            >>> device._check_command_output_has_error(command_resposne)
            CommandError: ...
            >>>
        """
        for error_keyword in self.error_keywords:
            if error_keyword in command_response:
                return True

        return False

    def _send_commands(
        self,
        netmiko_method: Callable[..., str],
        commands: Iterable[str],
        command_args: Mapping[str, Any],
    ) -> List[str]:
        """
        Send commands to device using ``netmiko_method``.

        Args:
            netmiko_method (netmiko.BaseConnection.send_command|netmiko.BaseConnection.send_config_set): The method to use to send the command(s) to the device.
            commands (list): The commands to send to the device.
            command_args (dict): The args to send when calling the netmiko method.

        Returns:
            list: The responses from sending ``commands`` to the device.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> netmiko_method = device.native.send_command
            >>> commands = ["show version", "show inventory"]
            >>> netmiko_args = {"delay_factor": 5}
            >>> device._send_commands(netmiko_method, commands, netmiko_args)
            ['...', '...']
            >>>
        """
        entered_commands: List[str] = []
        command_responses: List[str] = []
        try:
            for command in commands:
                entered_commands.append(command)
                command_response = netmiko_method(command, **command_args)
                command_responses.append(command_response)
                if self._check_command_output_has_error(command_response):
                    raise CommandError(command, command_response, entered_commands)
        except TypeError as err:
            raise TypeError(f"Netmiko Driver's {netmiko_method.__name__} {err.args[0]}")

        return command_responses

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

    def show(self, command: Union[str, Iterable[str]], **netmiko_args: Any) -> Union[str, List[str]]:
        """
        Send an operational command to the device.

        When ``command`` is a list, each command is sent to the device, and the
        output is checked for errors before proceeding to the next command in the list.
        If an error is detected, the remaining commands will not be sent to the device.

        Args:
            command (str|list): The commands to send to the device.
            **netmiko_args: Any argument support by ``netmiko.ConnectHandler.send_command``.

        Returns:
            str: When ``command`` is str, the data returned from the device.
            list: When ``command`` is list, the data returned from the device for each command.

        Raises:
            TypeError: When sending an argument in ``**netmiko_args`` that is not supported.
            CommandError: When ``command`` is str, and the returned data indicates the command failed.
            CommandListError: When ``command`` is list, and the return data indicates the command failed.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> version = device.show("show version")
            >>> print(version)
            'Cisco IOS Software, ...'
            >>> version = device.show(["show version", "show inventory"])
            >>> print(version)
            ['Cisco IOS Software, ...', 'NAME: "chassis", DESCR: ...']
            >>>
        """
        original_command_is_str: bool = isinstance(command, str)

        if original_command_is_str:
            command = [command]  # type: ignore [list-item]

        try:
            command_responses = self._send_commands(self.native.send_command, command, netmiko_args)
        # TODO: Remove this when deprecating CommandListError
        except CommandError as err:
            if not original_command_is_str:
                raise CommandListError(err.commands, err.command, err.cli_error_msg)
            else:
                raise err

        if original_command_is_str:
            return command_responses[0]

        return command_responses

    def show_list(self, commands: Iterable[str], **netmiko_args) -> List[str]:
        """
        DEPRECATED - Use the `show` method.

        Send operational commands to the device.

        Args:
            commands (list): The list of commands to send to the device.
            **netmiko_args: Any argument supported by ``netmiko.ConnectHandler.send_command``.

        Returns:
            list: The data returned from the device for all commands.

        Raises:
            TypeError: When sending an argument in ``**netmiko_args`` that is not supported.
            CommandListError: When the returned data indicates one of the commands failed.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> command_data = device.show_list(["show version", "show inventory"])
            >>> print(command_data[0])
            'Cisco IOS Software, ...'
            >>> print(command_data[1])
            'NAME: "chassis", DESCR: ...'
            >>>
        """
        warnings.warn("show_list() is deprecated; use show.", DeprecationWarning)
        return self.show(commands, **netmiko_args)  # type: ignore [return-value]
