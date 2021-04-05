"""Module for using a Cisco ASA device over SSH."""

import os
import re
import signal
import time
from collections import Counter
from typing import List, Dict, Union, Optional, Iterable
from ipaddress import ip_address, IPv4Address, IPv6Address, IPv4Interface, IPv6Interface

from netmiko import ConnectHandler
from netmiko.cisco import CiscoAsaSSH, CiscoAsaFileTransfer

from pyntc.utils import get_structured_data
from .base_device import BaseDevice, fix_docs
from pyntc.errors import (
    NTCError,
    CommandError,
    OSInstallError,
    CommandListError,
    FileTransferError,
    RebootTimeoutError,
    NTCFileNotFoundError,
    FileSystemNotFoundError,
)
from pyntc import log


RE_SHOW_FAILOVER_GROUPS = re.compile(r"Group\s+\d+\s+State:\s+(.+?)\s*$", re.M)
RE_SHOW_FAILOVER_STATE = re.compile(
    r"(?:Primary|Secondary)\s+-\s+(.+?)\s*$", re.M)
RE_SHOW_IP_ADDRESS = re.compile(
    r"^\S+\s+(\S+)\s+((?:\d+.){3}\d+)\s+((?:\d+.){3}\d+)", re.M)
RE_IPV6_INTERFACE_MATCH = re.compile(
    r"^\s+([A-Fa-f0-9:]{5,}).+?(/\d+)\s*$", re.M)


@fix_docs
class ASADevice(BaseDevice):
    """Cisco ASA Device Implementation."""

    vendor = "cisco"
    active_redundancy_states = {None, "active"}

    def __init__(self, host: str, username: str, password: str, secret="", port=22, **kwargs):
        """
        Pyntc Device constructor for Cisco ASA.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate to the device.
            password (str): The password to authenticate to the device.
            secret (str, optional): The password to escalate privlege on the device. Defaults to "".
            port (int, optional): Port used to establish connection. Defaults to 22.
        """
        super().__init__(host, username, password, device_type="cisco_asa_ssh")

        self.native: Optional[CiscoAsaSSH] = None
        self.secret = secret
        self.port = int(port)
        self.kwargs = kwargs
        self.global_delay_factor: int = kwargs.get("global_delay_factor", 1)
        self.delay_factor: int = kwargs.get("delay_factor", 1)
        self._connected = False
        self.open()
        self._peer_device: Optional[ASADevice] = None
        log.init(host=host)

    def _enable(self):
        log.warning("_enable() is deprecated; use enable().",
                    DeprecationWarning)
        self.enable()
        log.debug(f"Host {self.host}: Device enabled")

    def _enter_config(self):
        self.enable()
        self.native.config_mode()
        log.debug(f"Host {self.host}: Device entered config mode.")

    def _file_copy(self, src: str, dest: str, file_system: str) -> None:
        self.enable()

        if not self.file_copy_remote_exists(src, dest, file_system):
            fc: CiscoAsaFileTransfer = self._file_copy_instance(
                src, dest, file_system)

            try:
                fc.establish_scp_conn()
                fc.transfer_file()
            # Allow EOFErrors to be caught and only raise an error if the file is not actually on the device
            except EOFError:
                log.error(f"Host {self.host}: EOF error.")
                self.open()
            except Exception:
                log.error(
                    f"Host {self.host}: File transfer error {FileTransferError.default_message}")
                raise FileTransferError
            finally:
                log.error(
                    f"Host {self.host}: An error occurred when transferring file {src}.")
                fc.close_scp_chan()

            if not self.file_copy_remote_exists(src, dest, file_system):
                log.error(
                    f"Host {self.host}: Attempted file copy, but could not validate file {src} existed after transfer."
                )
                raise FileTransferError

        log.info(f"Host {self.host}: File transferred successfully.")

    def _file_copy_instance(
        self, src: str, dest: Optional[str] = None, file_system: str = "flash:"
    ) -> CiscoAsaFileTransfer:
        if dest is None:
            dest = os.path.basename(src)

        fc = CiscoAsaFileTransfer(
            self.native, src, dest, file_system=file_system)
        log.debug(f"Host {self.host}: File copy instance {fc}.")
        return fc

    def _get_file_system(self):
        """Determine the default file system or directory for device.

        Returns:
            str: The name of the default file system or directory for the device.

        Raises:
            FileSystemNotFound: When the module is unable to determine the default file system.
        """
        raw_data = self.show("dir")
        try:
            file_system = re.match(r"\s*.*?(\S+:)", raw_data).group(1)

        except AttributeError:
            # TODO: Get proper hostname
            log.error(
                f"Host {self.host}: File system not found with command 'dir'.")
            raise FileSystemNotFoundError(hostname=self.host, command="dir")

        log.debug(f"Host {self.host}: File system {file_system}.")
        return file_system

    def _get_ipv4_addresses(self, host: str) -> Dict[str, List[IPv4Address]]:
        """
        Get IPv4 Addresses for ``host``.

        Args:
            host (str): Whether to get IP Addresses for `self` or `peer` device.

        Returns:
            dict: The list of ``ip_interface`` objects mapped to their associated interface.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev._get_ipv4_addresses("self")
            {'outside': [IPv4Interface('10.132.8.6/24')], 'inside': [IPv4Interface('10.1.1.2/23')]}
            >>> dev._get_ipv4_addresses("peer")
            {'outside': [IPv4Interface('10.132.8.7')], 'inside': [IPv4Interface('10.1.1.3')]}
            >>>
        """
        if host == "self":
            command = "show ip address"
        elif host == "peer":
            command = "failover exec mate show ip address"

        show_ip_address = self.show(command)
        re_ip_addresses = RE_SHOW_IP_ADDRESS.findall(show_ip_address)

        # ??? log.debug
        results = {
            interface: [IPv4Interface(f"{address}/{netmask}")] for interface, address, netmask in re_ip_addresses
        }
        log.debug(f"Host {self.host}: ip interfaces {results}")
        return results

    def _get_ipv6_addresses(self, host: str) -> Dict[str, List[IPv6Address]]:
        """
        Get IPv6 Addresses for ``host``.

        Args:
            host (str): Whether to get IP Addresses for `self` or `peer` device.

        Returns:
            dict: The list of ``ip_interface`` objects mapped to their associated interface.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev._get_ipv6_addresses("self")
            {'outside': [IPv6Interface('fe80::2a0:c9ff:fe03:101')]}
            >>> dev._get_ipv6_addresses("peer")
            {'outside': [IPv6Interface('fe80::2a0:c9ff:fe03:102')]}
            >>>
        """
        if host == "self":
            command = "show ipv6 interface"
        elif host == "peer":
            command = "failover exec mate show ipv6 interface"

        show_ipv6_interface = self.show(command)
        show_ipv6_interface_lines: List[str] = show_ipv6_interface.strip(
        ).splitlines()
        first_line = show_ipv6_interface_lines.pop(0)
        interface: str = first_line.split()[0]
        ipv6_addresses: List[IPv6Interface] = []
        results: Dict[str, List] = {}
        for line in show_ipv6_interface_lines:
            # match IPv6 addresses under interface line
            if line[0].isspace():
                match = RE_IPV6_INTERFACE_MATCH.match(line)
                if match:
                    ipv6_addresses.append(IPv6Interface(
                        f"{match.group(1)}{match.group(2)}"))
            # update results mapping interface to matched IPv6 addresses and generate the next interface name
            else:
                if ipv6_addresses:
                    results[interface] = ipv6_addresses
                    ipv6_addresses = []
                interface = line.split()[0]

        # Add final interface in iteration if it has IPv6 addresses
        if ipv6_addresses:
            results[interface] = ipv6_addresses

        log.debug(f"Host {self.host}: ip interfaces {results}")
        return results

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show version")
        if re.search(image_name, version_data):
            log.info(
                f"Host {self.host}: Image {image_name} booted successfully.")
            return True

        log.info(
            f"Host {self.host}: Image {image_name} not booted successfully.")
        return False

    def _interfaces_detailed_list(self):
        ip_int = self.show("show interface")
        ip_int_data = get_structured_data(
            "cisco_asa_show_interface.template", ip_int)

        log.debug(f"Host {self.host}: interfaces detailed list {ip_int_data}.")
        return ip_int_data

    def _raw_version_data(self):
        show_version_out = self.show("show version")
        try:
            version_data = get_structured_data(
                "cisco_asa_show_version.template", show_version_out)[0]

            log.debug(f"Host {self.host}: version data {version_data}.")
            return version_data
        except IndexError:
            log.error(f"Host {self.host}: index error.")
            return {}

    def _send_command(self, command, expect_string=None):
        if expect_string is None:
            response = self.native.send_command_timing(command)
        else:
            response = self.native.send_command(
                command, expect_string=expect_string)

        if "% " in response or "Error:" in response:
            log.error(
                f"Host {self.host}: Error in {command} with response: {response}")
            raise CommandError(command, response)

        log.info(
            f"Host {self.host}: Command {command} was executed successfully with response: {response}")
        return response

    def _show_vlan(self):
        show_vlan_out = self.show("show vlan")
        show_vlan_data = get_structured_data(
            "cisco_ios_show_vlan.template", show_vlan_out)

        log.debug(
            f"Host {self.host}: Successfully executed command 'show vlan' with responses {show_vlan_data}.")
        return show_vlan_data

    def _uptime_components(self, uptime_full_string):
        match_days = re.search(r"(\d+) days?", uptime_full_string)
        match_hours = re.search(r"(\d+) hours?", uptime_full_string)
        match_minutes = re.search(r"(\d+) minutes?", uptime_full_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0

        return days, hours, minutes

    def _uptime_to_seconds(self, uptime_full_string):
        days, hours, minutes = self._uptime_components(uptime_full_string)

        seconds = days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60

        return seconds

    def _uptime_to_string(self, uptime_full_string):
        days, hours, minutes = self._uptime_components(uptime_full_string)
        return "%02d:%02d:%02d:00" % (days, hours, minutes)

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                log.debug(f"Host {self.host}: Device rebooted.")
                return
            except:  # noqa E722 # nosec
                pass

        # TODO: Get proper hostname parameter
        log.error(f"Host {self.host}: Device timed out while rebooting.")
        raise RebootTimeoutError(hostname=self.host, wait_time=timeout)

    def _wait_for_peer_reboot(self, acceptable_states: Iterable[str], timeout: int = 3600) -> None:
        """
        Wait for peer device to come online and reach an acceptable state.

        Args:
            acceptable_states (iter): A list of states that are acceptable for considering peer to be ready.
            timeout (int): The maximum amount of time to wait for peer device to be online and reach a state in ``acceptable_states``.

        Raises:
            RebootTimeoutError: When the ``timeout`` value has been reached and the peer has not reached a state in ``acceptable_states``.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev.peer_redundancy_state
            'standby ready'
            >>> dev.show("failover reload-standby")
            >>> dev._wait_for_peer_reboot(acceptable_states=["standy ready"])
            RebootTimeoutError...
            >>> dev.peer_redundancy_state
            'cold standby'
            >>> dev.show("failover reload-standby")
            >>> dev._wait_for_peer_reboot(acceptable_states=["cold-standby", "standy ready"])
            >>> dev.peer_redundancy_state
            'cold standby'
            >>>
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.peer_redundancy_state == "failed":
                log.error(
                    f"Host {self.host}: Redundancy state for device {self.host} did not form properly to desired state: {self.peer_redundancy_state}."
                )
                break

        while time.time() - start < timeout:
            if self.peer_redundancy_state in acceptable_states:
                return
            time.sleep(1)

        # TODO: Get proper hostname parameter
        log.error(
            f"Host {self.host}: reboot timeout error with timeout {timeout}.")
        raise RebootTimeoutError(
            hostname=f"{self.host}-peer", wait_time=timeout)

    def backup_running_config(self, filename):
        """
        Backups running config.

        Args:
            filename (str): Name of backup file.
        """
        with open(filename, "w") as f:
            f.write(self.running_config)

        log.debug(
            f"Host {self.host}: Running config backed up to {self.running_config}.")

    @property
    def boot_options(self):
        """
        Determine boot image.

        Returns:
            dict: Key: 'sys' Value: Current boot image.
        """
        show_boot_out = self.show("show boot | i BOOT variable")
        # Improve regex to get only the first boot $var in the sequence!
        boot_path_regex = r"Current BOOT variable = (\S+):\/(\S+)"

        match = re.search(boot_path_regex, show_boot_out)
        if match:
            boot_image = match.group(2)
        else:
            boot_image = None

        log.debug(
            f"Host {self.host}: the boot options are {dict(sys=boot_image)}")
        return dict(sys=boot_image)

    def checkpoint(self, checkpoint_file):
        """
        Create a checkpoint file of the current config.

        Args:
            checkpoint_file (str):  Saves a checkpoint file with the name provided to the function.
        """
        log.debug(f"Host {self.host}: checkpoint is {checkpoint_file}.")
        self.save(filename=checkpoint_file)

    def close(self):
        """Disconnect from device."""
        if self._connected:
            self.native.disconnect()
            self._connected = False
            log.debug("Host {self.host}: Connection closed.")

    def config(self, command):
        """
        Send single command to device.

        Args:
            command (str): command to be sent to device.
        """
        self._enter_config()
        self._send_command(command)
        self.native.exit_config_mode()
        log.info(f"Host {self.host}: Device configured with command {command}.")

    def config_list(self, commands):
        """
        Send list of commands to device.

        Args:
            commands (list): list of commands to be set to device.

        Raises:
            CommandListError: Message stating which command failed and the response from the device.
        """
        self._enter_config()
        entered_commands = []
        for command in commands:
            entered_commands.append(command)
            try:
                self._send_command(command)
            except CommandError as e:
                log.error(
                    f"Host {self.host}: Command error with commands: {entered_commands} and error message {e.cli_error_msg}"
                )
                raise CommandListError(
                    entered_commands, command, e.cli_error_msg)
        log.info(
            f"Host {self.host}: Configured with commands: {entered_commands}")
        self.native.exit_config_mode()

    @property
    def connected_interface(self) -> str:
        """
        Interface that is assigned an IP Address of ``self.ip_address``.

        Returns:
            str: The name of the interfaces associated to ``self.ip_address``.

        Example:
            >>> dev = ASADevice("10.1.1.1", **connection_args)
            >>> dev.connected_interface
            'management'
            >>>
        """
        address = self.ip_address
        ip_property = getattr(self, f"{self.ip_protocol}_addresses")
        for interface, addresses in ip_property.items():
            addrs = {ip_address(addr.ip) for addr in addresses}
            if address in addrs:
                connected_interface = interface
                break

        # TODO: Raise custom exception for when connected_interface is not discovered
        log.debug(
            f"Host {self.host}: Interface connected to {address} is {connected_interface}.")
        return connected_interface

    def enable(self):
        """Ensure device is in enable mode.

        Returns:
            None: Device prompt is set to enable mode.
        """
        # Netmiko reports enable and config mode as being enabled
        if not self.native.check_enable_mode():
            self.native.enable()
        # Ensure device is not in config mode
        if self.native.check_config_mode():
            self.native.exit_config_mode()

        log.debug(f"Host {self.host}: Device enabled.")

    def enable_scp(self) -> None:
        """
        Enable SCP on device by configuring "ssh scopy enable".

        The command is ran on the active device; if the device is
        currently standby, then a new connection is created to the
        active device. The configuration is saved after to sync to peer.

        Raises:
            FileTransferError: When unable to configure scopy on the active device.

        Example:
            >>> device = ASADevice(**connection_args)
            >>> device.show("show run ssh | i scopy")
            ''
            >>> device.enable_scp()
            >>> device.show("show run ssh | i scopy")
            'ssh scopy enable'
            >>>
        """
        if self.is_active():
            device: ASADevice = self
        else:
            device = self.peer_device

        if not device.is_active():
            log.error(
                f"Host {self.host}: Unable to establish a connection with the active device")
            raise FileTransferError

        try:
            device.config("ssh scopy enable")
        except CommandError:
            log.error(f"Host {self.host}: Unable to enable scopy on the device")
            raise FileTransferError

        log.info(f"Host {self.host}: ssh copy enabled.")
        device.save()

    @property
    def facts(self):
        """Implement this once facts re-factor is done."""
        return {}

    def file_copy(
        self,
        src: str,
        dest: Optional[str] = None,
        file_system: Optional[str] = None,
        peer: Optional[bool] = False,
    ) -> None:
        """
        Copy ``src`` file to device.

        The ``src`` file can be copied to both the device and its peer by
        setting ``peer`` to True. If transferring to the peer device, the
        transfer will use the address associated with the ``peer_interface``
        from "show failover" output.

        Args:
            src (str): The path to the file to be copied to the device.
            dest (str): The name to use for storing the file on the device.
                Default is to use the name of the ``src`` file.
            file_system (str): The directory to store the file on the device.
                Default will use ``_get_file_system()`` to determine the default file_system.
            peer (bool): Whether to transfer the ``src`` file to the peer device.

        Raises:
            FileTransferError: When the ``src`` file is unable to transfer the file to any device.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev.file_copy("path/to/asa-image.bin", peer=True)
        """
        if dest is None:
            dest = os.path.basename(src)

        if file_system is None:
            file_system = self._get_file_system()

        # netmiko's enable_scp
        self.enable_scp()
        self._file_copy(src, dest, file_system)
        if peer:
            self.peer_device._file_copy(src, dest, file_system)

        log.info(f"Host {self.host}: File {src} transferred successfully.")

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, file_system=None):
        """
        Copy ``src`` file to device.

        Args:
            src (str): The path to the file to be copied to the device.
            dest (str, optional): The name to use for storing the file on the device.
                Defaults to use the name of the ``src`` file..
            file_system (str, optional): The directory name to store files on the device.
                Defaults to discover the default directory of the device.

        Returns:
            bool: True if the file exists on the device and the md5 hashes match. Otherwise, false.

        Example:
        >>> status = file_copy_remote_exists("path/to/asa-image.bin")
        >>> print(status)
        True
        >>>
        """
        self.enable()
        if file_system is None:
            file_system = self._get_file_system()

        fc = self._file_copy_instance(src, dest, file_system=file_system)
        if fc.check_file_exists() and fc.compare_md5():
            log.debug(f"Host {self.host}: File {src} already exists on remote.")
            return True

        log.debug(
            f"Host {self.host}: File {src} does not already exist on remote.")
        return False

    def install_os(self, image_name, **vendor_specifics):
        """
        Install OS on device.

        Args:
            image_name (str): Name of the image to be installed.

        Raises:
            OSInstallError: Message stating the end device could not boot into the new image.

        Returns:
            bool: True if new image is installed correctly. False if device is already running image_name.
        """
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            self.set_boot_options(image_name, **vendor_specifics)
            self.reboot()
            self._wait_for_device_reboot(timeout=timeout)
            if not self._image_booted(image_name):
                log.error(
                    f"Host {self.host}: OS install error for image {image_name}")
                raise OSInstallError(hostname=self.facts.get(
                    "hostname"), desired_boot=image_name)

            log.info(
                f"Host {self.host}: OS image {image_name} installed successfully.")
            return True

        log.info(f"Host {self.host}: OS image {image_name} not installed.")
        return False

    @property
    def ip_address(self) -> Union[IPv4Address, IPv6Address]:
        """
        IP Address used to establish the connection to the device.

        Returns:
            IPv4Address/IPv6Address: The IP address used by the paramiko connection.

        Raises:
            ValueError: When a valid IP Address is unable to be derived from ``self.host``.

        Example:
            >>> dev = ASADevice("10.1.1.1", **connection_args)
            >>> dev.ip_address
            IPv4Address('10.1.1.1')
            >>> dev = ASADevice("asa_host", **connection_args)
            >>> dev.ip_address
            IPv6Address('fe80::2a0:c9ff:fe03:102')
            >>>
        """
        try:
            ip = ip_address(self.host)
        except ValueError:
            # Assume hostname was used, and retrieve resolved IP from paramiko transport
            log.error(
                f"Host {self.host}: value error for ip address used to establish connection.")
            ip = ip_address(self.native.remote_conn.transport.getpeername()[0])

        log.debug(
            f"Host {self.host}: ip address used to establish connection {ip}.")
        return ip

    @property
    def ipv4_addresses(self) -> Dict[str, List[IPv4Address]]:
        """
        IPv4 addresses of the device's interfaces.

        Returns:
            dict: The ipv4 addresses mapped to their interfaces.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev.ipv4_addresses
            {'outside': [IPv4Interface('10.132.8.6/24')], 'inside': [IPv4Interface('10.1.1.2/23')]}
            >>>
        """
        log.debug(
            f"Host {self.host}: ipv4 addresses of the devices interfaces {self._get_ipv4_addresses('self')}.")
        return self._get_ipv4_addresses("self")

    @property
    def ipv6_addresses(self) -> Dict[str, List[IPv6Address]]:
        """
        IPv6 addresses of the device's interfaces.

        Returns:
            dict: The ipv6 addresses mapped to their interfaces.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev.ipv6_addresses
            {'outside': [IPv6Interface('fe80::5200:ff:fe0a:1')]}
            >>>
        """
        log.debug(
            f"Host {self.host}: ipv6 addresses of the devices interfaces {self._get_ipv6_addresses('self')}.")
        return self._get_ipv6_addresses("self")

    @property
    def ip_protocol(self) -> str:
        """
        IP Protocol of the IP Addressed used by the underlying paramiko connection.

        Returns:
            str: "ipv4" for IPv4 Addresses and "ipv6" for IPv6 Addresses.

        Raises:
            ValueError: When ``self.ip_address`` is unable to derive a valid IP Address.

        Example:
            >>> dev = ASADevice("10.1.1.1", **connection_args)
            >>> dev.ip_protocol
            'ipv4'
            >>> dev = ASADevice("asa_host", **connection_args)
            >>> dev.ip_protocol
            'ipv6'
            >>>
        """
        protocol = f"ipv{self.ip_address.version}"

        log.debug(f"Host {self.host}: IP protocol for paramiko is {protocol}.")
        return protocol

    def is_active(self):
        """
        Determine if the current processor is the active processor.

        Returns:
            bool: True if the processor is active or does not support HA, else False.

        Example:
            >>> device = ASADevice(**connection_args)
            >>> device.is_active()
            True
            >>>
        """
        return self.redundancy_state in self.active_redundancy_states

    def open(self):
        """Attempt to find device prompt. If not found, create Connecthandler object to device."""
        if self._connected:
            try:
                self.native.find_prompt()
            except:  # noqa E722
                self._connected = False

        if not self._connected:
            self.native = ConnectHandler(
                device_type="cisco_asa",
                ip=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                global_delay_factor=self.global_delay_factor,
                secret=self.secret,
                verbose=False,
            )
            self._connected = True

        log.debug(
            f"Host {self.host}: Connection to controller was opened successfully.")

    @property
    def peer_device(self) -> "ASADevice":
        """
        Create instance of ASADevice for peer device.

        Returns:
            :class`~devices.ASADevice`: Cisco ASA device instance.
        """
        if self._peer_device is None:
            self._peer_device = self.__class__(
                str(self.peer_ip_address), self.username, self.password, self.secret, self.port, **self.kwargs
            )
        else:
            self._peer_device.open()

        log.debug(f"Host {self.host}: Peer device {self._peer_device}.")
        return self._peer_device

    @property
    def peer_ip_address(self) -> Union[IPv4Address, IPv6Address]:
        """
        IP Address associated with ``self.ip_address`` on the peer device.

        Returns:
            IPv4Address/IPv6Address: The IP address used by the paramiko connection.

        Raises:
            ValueError: When a valid IP Address is unable to be derived from ``self.host``.

        Example:
            >>> dev = ASADevice("10.1.1.1", **connection_args)
            >>> dev.peer_ip_address
            IPv4Address('10.1.1.2')
            >>> dev = ASADevice("asa_host", **connection_args)
            >>> dev.peer_ip_address
            IPv6Address('fe80::2a0:c9ff:fe03:103')
            >>>
        """
        self_address = self.ip_address
        peer_ip_property = getattr(self, f"peer_{self.ip_protocol}_addresses")
        peer_ip_addresses = peer_ip_property[self.connected_interface]
        for address in peer_ip_addresses:
            if self_address in address.network:
                log.debug(f"Host {self.host}: Peer IP {address.ip}.")
                return address.ip

    @property
    def peer_ipv4_addresses(self) -> Dict[str, List[IPv4Address]]:
        """
        IPv4 addresses of the peer device's interfaces.

        Returns:
            dict: The ipv4 addresses mapped to their interfaces.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev.peer_ipv4_addresses
            {'outside': [IPv4Address('10.132.8.7')], 'inside': [IPv4Address('10.1.1.3')]}
            >>>
        """
        return self._get_ipv4_addresses("peer")

    @property
    def peer_ipv6_addresses(self) -> Dict[str, List[IPv6Address]]:
        """
        IPv6 addresses of the peer device's interfaces.

        Returns:
            dict: The ipv6 addresses mapped to their interfaces.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev.peer_ipv6_addresses
            {'outside': [IPv6Address('fe80::5200:ff:fe0a:2')]}
            >>>
        """
        return self._get_ipv6_addresses("peer")

    @property
    def peer_redundancy_state(self):
        """
        Determine the current redundancy state of the peer processor.

        In the case of multi-context configurations, a peer will be considered
        active if it is the active device for any context. Otherwise, the most
        common state will be returned.

        Returns:
            str: The redundancy state of the peer processor.
            None: When the processor does not support redundancy.

        Example:
            >>> device = ASADevice(**connection_args)
            >>> device.peer_redundancy_state
            'standby ready'
            >>>
        """
        try:
            show_failover = self.show("show failover")
        except CommandError:
            log.error(f"Host {self.host}: Peer redundancy state command error.")
            return None

        if "Failover On" in show_failover:
            peer_failover_data = show_failover.split("Other host:")[1]
            show_failover_groups = RE_SHOW_FAILOVER_GROUPS.findall(
                peer_failover_data)
            if not show_failover_groups:
                re_show_failover_peer_state = RE_SHOW_FAILOVER_STATE.search(
                    peer_failover_data)
                peer_redundancy_state = re_show_failover_peer_state.group(1)
            else:
                if "Active" in show_failover_groups:
                    peer_redundancy_state = "active"
                else:
                    peer_redundancy_state_counter = Counter(
                        show_failover_groups)
                    peer_redundancy_state = peer_redundancy_state_counter.most_common()[
                        0][0]
        else:
            peer_redundancy_state = "disabled"

        log.debug(
            f"Host {self.host}: Peer redundancy state: {peer_redundancy_state}.")
        return peer_redundancy_state.lower()

    def reboot(self, timer=0, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            timer (int, optional): The time to wait before reloading. Defaults to 0.

        Raises:
            RebootTimeoutError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = ASADevice(**connection_args)
            >>> device.reboot()
            >>>
        """
        if kwargs.get("confirm"):
            log.warning(
                "Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        def handler(signum, frame):
            log.error(f"Host {self.host}: Interrupting after reload.")
            raise RebootSignal

        signal.signal(signal.SIGALRM, handler)
        signal.alarm(10)

        try:
            if timer > 0:
                first_response = self.show("reload in %d" % timer)
            else:
                first_response = self.show("reload")

            if "System configuration" in first_response:
                self.native.send_command_timing("no")

            self.native.send_command_timing("\n")
        except RebootSignal:
            signal.alarm(0)

        signal.alarm(0)

        log.info(f"Host {self.host}: Device rebooted.")

    def reboot_standby(self, acceptable_states: Optional[Iterable[str]] = None, timeout: Optional[int] = None) -> None:
        """
        Reload the standby device from the active device.

        Args:
            acceptable_states (iter): List of acceptable redundancy states for the peer device after reboot.
                Default will use the current value of ``peer_redundancy_state``.
            timeout (int): The maximum time to wait for the device to boot back into an ``acceptable_state``.

        Raises:
            RebootTimeoutError: When ``timeout`` is reached before the peer reaches a state in ``acceptable_states``.

        Example:
            >>> dev = ASADevice(**connection_args)
            >>> dev.peer_redundancy_state
            'standby ready'
            >>> dev.reboot_standby()
            RebootTimeoutError...
            >>> dev.peer_redundancy_state
            'cold standby'
            >>> dev.reboot_standby(acceptbale_states=["standby ready", "cold standby"])
            >>> dev.peer_redundancy_state
            'cold standby'
            >>>
        """
        if acceptable_states is None:
            acceptable_states = [self.peer_redundancy_state]
        kwargs = {"acceptable_states": acceptable_states}
        if timeout is not None:
            kwargs["timeout"] = timeout
        self.show("failover reload-standby")
        self._wait_for_peer_reboot(**kwargs)

        log.debug(f"Host {self.host}: reboot standby with timeout {timeout}.")

    @property
    def redundancy_mode(self):
        """
        Operating redundancy mode of the device.

        Returns:
            str: The redundancy mode the device is operating in.
                If the command is not supported, then "n/a" is returned.

        Example:
            >>> device = ASADevice(**connection_args)
            >>> device.redundancy_mode
            'on'
            >>>
        """
        try:
            show_failover = self.show("show failover")
        except CommandError:
            return "n/a"

        show_failover_first_line = show_failover.splitlines()[0].strip()
        redundancy_mode = show_failover_first_line.lower().lstrip("failover")
        log.debug(
            f"Host {self.host}: Redundancy mode: {redundancy_mode.lstrip()}")
        return redundancy_mode.lstrip()

    @property
    def redundancy_state(self):
        """
        Determine the current redundancy state of the processor.

        In the case of multi-context configurations, a device will be considered
        active if it is the active device for any context. Otherwise, the most
        common state will be returned.

        Returns:
            str: The redundancy state of the processor.
            None: When the processor does not support redundancy.

        Example:
            >>> device = ASADevice(**connection_args)
            >>> device.redundancy_state
            'active'
            >>>
        """
        try:
            show_failover = self.show("show failover")
        except CommandError:
            log.error(f"Host {self.host}: Redundancy state command error.")
            return None

        if "Failover On" in show_failover:
            failover_data = show_failover.split("Other host:")[0]
            show_failover_groups = RE_SHOW_FAILOVER_GROUPS.findall(
                failover_data)
            if not show_failover_groups:
                re_show_failover_state = RE_SHOW_FAILOVER_STATE.search(
                    failover_data)
                redundancy_state = re_show_failover_state.group(1)
            else:
                if "Active" in show_failover_groups:
                    redundancy_state = "active"
                else:
                    redundancy_state_counter = Counter(show_failover_groups)
                    redundancy_state = redundancy_state_counter.most_common()[
                        0][0]
        else:
            redundancy_state = "disabled"

        log.debug(
            f"Host {self.host}: Redundancy state {redundancy_state.lower()}.")
        return redundancy_state.lower()

    def rollback(self, rollback_to):
        """
        Rollback the device configuration.

        Args:
            rollback_to (str): Name of checkpoint file to rollback to

        Raises:
            NotImplementedError: Function not implemented yet.
        """
        raise NotImplementedError

    @property
    def running_config(self):
        """
        Get current running config on device.

        Returns:
            str: Running configuration on device.
        """
        return self.show("show running-config")

    def save(self, filename="startup-config"):
        """
        Save changes to startup config.

        Args:
            filename (str, optional): Name of startup configuration file. Defaults to "startup-config".

        Returns:
            bool: True if configuration saved succesfully.
        """
        command = "copy running-config %s" % filename
        # Changed to send_command_timing to not require a direct prompt return.
        self.native.send_command_timing(command)
        # If the user has enabled 'file prompt quiet' which dose not require any confirmation or feedback.
        # This will send return without requiring an OK.
        # Send a return to pass the [OK]? message - Increase delay_factor for looking for response.
        self.native.send_command_timing("\n", delay_factor=2)
        # Confirm that we have a valid prompt again before returning.
        self.native.find_prompt()
        log.debug(f"Host {self.host}: Configuration saved.")
        return True

    def set_boot_options(self, image_name, **vendor_specifics):
        """
        Set new image as boot option on device.

        Args:
            image_name (str): AName of image.

        Raises:
            NTCFileNotFoundError: File not found on device.
            CommandError: Unable to issue command on device.
        """
        current_boot = self.show("show running-config | inc ^boot system ")
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = self._get_file_system()

        file_system_files = self.show("dir {0}".format(file_system))
        if re.search(image_name, file_system_files) is None:
            log.error(
                f"Host {self.host}: File not found error for image {image_name}.")
            raise NTCFileNotFoundError(
                # TODO: Update to use hostname
                hostname=self.host,
                file=image_name,
                dir=file_system,
            )

        current_images = current_boot.splitlines()
        commands_to_exec = ["no {0}".format(image) for image in current_images]
        commands_to_exec.append(
            "boot system {0}/{1}".format(file_system, image_name))
        self.config_list(commands_to_exec)

        self.save()
        if self.boot_options["sys"] != image_name:
            log.error(
                f"Host {self.host}: Setting boot command did not yield expected results")
            raise CommandError(
                command="boot system {0}/{1}".format(file_system, image_name),
                message="Setting boot command did not yield expected results",
            )

        log.info(
            f"Host {self.host}: boot options have been set to {image_name}")

    def show(self, command, expect_string=None):
        """
        Send command to device.

        Args:
            command (str): Command to be ran on device.
            expect_string (str, optional): Expected response from running command on device. Defaults to None.

        Returns:
            str: Output from running command on device.
        """
        self.enable()
        log.debug(
            f"Host {self.host}: Successfully executed command 'show' with responses.")
        return self._send_command(command, expect_string=expect_string)

    def show_list(self, commands):
        """
        Send list of commands to device.

        Args:
            commands (list): Commands to be sent to device.

        Raises:
            CommandListError: Failure running command on device.

        Returns:
            list: Output from each command sent.
        """
        self.enable()

        responses = []
        entered_commands = []
        for command in commands:
            entered_commands.append(command)
            try:
                responses.append(self._send_command(command))
            except CommandError as e:
                log.error(
                    f"Host {self.host}: Command error for commands {entered_commands} with message {e.cli_error_msg}."
                )
                raise CommandListError(
                    entered_commands, command, e.cli_error_msg)

        log.debug(
            f"Host {self.host}: Successfully executed command 'show' with responses {responses}.")
        return responses

    @property
    def startup_config(self):
        """
        Show startup config.

        :return: Output of command 'show startup-config'.
        """
        return self.show("show startup-config")


class RebootSignal(NTCError):
    """Not implemented."""

    pass
