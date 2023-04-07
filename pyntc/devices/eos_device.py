"""Module for using an Arista EOS device over the eAPI."""

import os
import re
import time

from netmiko import ConnectHandler, FileTransfer
from pyeapi import connect as eos_connect
from pyeapi.client import Node as EOSNative
from pyeapi.eapilib import CommandError as EOSCommandError

from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs, RollbackError
from pyntc.devices.system_features.vlans.eos_vlans import EOSVlans
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    FileTransferError,
    NTCError,
    NTCFileNotFoundError,
    OSInstallError,
    RebootTimeoutError,
)
from pyntc.utils import convert_list_by_key


BASIC_FACTS_KM = {"model": "modelName", "os_version": "internalVersion", "serial_number": "serialNumber"}
INTERFACES_KM = {
    "speed": "bandwidth",
    "duplex": "duplex",
    "vlan": ["vlanInformation", "vlanId"],
    "state": "linkStatus",
    "description": "description",
}


@fix_docs
class EOSDevice(BaseDevice):
    """Arista EOS Device Implementation."""

    vendor = "arista"

    def __init__(self, host, username, password, transport="http", port=None, timeout=None, **kwargs):  # noqa: D403
        """PyNTC Device implementation for Arista EOS.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            transport (str): The protocol to communicate with the device. Defaults to http.
            port (int): The port to use to establish the connection. Defaults to None.
            timeout(int): Timeout value used for connection with the device. Defaults to None.
        """
        super().__init__(host, username, password, device_type="arista_eos_eapi")
        self.transport = transport
        self.port = port
        self.timeout = timeout
        eapi_args = {
            "transport": transport,
            "host": host,
            "username": username,
            "password": password,
        }
        optional_args = ("port", "timeout")
        for arg in optional_args:
            value = getattr(self, arg)
            if value is not None:
                eapi_args[arg] = value
        self.connection = eos_connect(**eapi_args)
        self.native = EOSNative(self.connection)
        # _connected indicates Netmiko ssh connection
        self._connected = False
        log.init(host=host)

    def _file_copy_instance(self, src, dest=None, file_system="flash:"):
        if dest is None:
            dest = os.path.basename(src)

        file_copy = FileTransfer(self.native_ssh, src, dest, file_system=file_system)
        log.debug("Host %s: File copy instance %s.", self.host, file_copy)
        return file_copy

    def _get_file_system(self):
        """Determine the default file system or directory for device.

        Returns:
            str: The name of the default file system or directory for the device.

        Raises:
            FileSystemNotFound: When the module is unable to determine the default file system.
        """
        raw_data = self.show("dir", raw_text=True)
        try:
            file_system = re.match(r"\s*.*?(\S+:)", raw_data).group(1)
        except AttributeError:
            log.error("Host %s: Attribute error with command 'dir'.", self.host)
            raise FileSystemNotFoundError(hostname=self.hostname, command="dir")

        log.debug("Host %s: File system %s.", self.host, file_system)
        return file_system

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show boot", raw_text=True)
        if re.search(image_name, version_data):
            log.info("Host %s: Image %s booted successfully.", self.host, image_name)
            return True

        return False

    def _interfaces_status_list(self):
        interfaces_list = []
        interfaces_status_dictionary = self.show("show interfaces status")["interfaceStatuses"]
        for key in interfaces_status_dictionary:
            interface_dictionary = interfaces_status_dictionary[key]
            interface_dictionary["interface"] = key
            interfaces_list.append(interface_dictionary)

        interface_status_list = convert_list_by_key(
            interfaces_list, INTERFACES_KM, fill_in=True, whitelist=["interface"]
        )
        log.debug("Host %s: interfaces detailed list %s.", self.host, interface_status_list)
        return interface_status_list

    def _parse_response(self, response, raw_text):  # pylint: disable=no-self-use
        if raw_text:
            return list(x["result"]["output"] for x in response)

        return list(x["result"] for x in response)

    def _uptime_to_string(self, uptime):  # pylint: disable=no-self-use
        days = uptime / (24 * 60 * 60)
        uptime = uptime % (24 * 60 * 60)

        hours = uptime / (60 * 60)
        uptime = uptime % (60 * 60)

        mins = uptime / 60
        uptime = uptime % 60

        seconds = uptime

        return f"{days:02d}:{hours:02d}:{mins:02d}:{seconds:02d}"

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.show("show hostname")
                log.debug("Host %s: Device rebooted.", self.host)
                return
            except:  # noqa E722 # nosec  # pylint: disable=bare-except
                pass

        log.error("Host %s: Device timed out while rebooting.", self.host)
        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        """
        Create backup file of running configuration.

        Args:
            filename (str): The name of the file that will be saved.
        """
        with open(filename, "w", encoding="utf-8") as file_name:
            file_name.write(self.running_config)

        log.debug("Host %s: Running config backed up to %s.", self.host, self.running_config)

    @property
    def boot_options(self):
        """Get current running software.

        Returns:
            dict: Key is ``sys`` with value being the image on the device.
        """
        image = self.show("show boot-config")["softwareImage"]
        image = image.replace("flash:", "")
        log.debug("Host %s: the boot options are %s", self.host, dict(sys=image))
        return dict(sys=image)

    def checkpoint(self, checkpoint_file):
        """Copy running config checkpoint.

        Args:
            checkpoint_file (str): Checkpoint file name.
        """
        log.debug("Host %s: checkpoint is %s.", self.host, checkpoint_file)
        self.show(f"copy running-config {checkpoint_file}")

    def close(self):
        """Not implemented. Just ``passes``."""
        pass  # pylint: disable=unnecessary-pass

    def config(self, commands):
        """Send configuration commands to a device.

        Args:
            commands (str, list): String with single command, or list with multiple commands.

        Raises:
            CommandError: Issue with the command provided.
            CommandListError: Issue with a command in the list provided.
        """
        try:
            self.native.config(commands)
            log.info("Host %s: Device configured with commands %s.", self.host, commands)
        except EOSCommandError as e:
            if isinstance(commands, str):
                log.error(
                    "Host %s: Command error with commands: %s and error message %s", self.host, commands, e.message
                )
                raise CommandError(commands, e.message)
            raise CommandListError(commands, e.commands[len(e.commands) - 1], e.message)

    def enable(self):
        """Ensure device is in enable mode.

        Returns:
            None: Device prompt is set to enable mode.
        """
        # Netmiko reports enable and config mode as being enabled
        if not self.native_ssh.check_enable_mode():
            self.native_ssh.enable()
        # Ensure device is not in config mode
        if self.native_ssh.check_config_mode():
            self.native_ssh.exit_config_mode()

        log.debug("Host %s: Device enabled", self.host)

    @property
    def uptime(self):
        """
        Get uptime of the device in seconds.

        Returns:
            int: Uptime of the device.
        """
        if self._uptime is None:
            sh_version_output = self.show("show version")
            self._uptime = int(time.time() - sh_version_output["bootupTimestamp"])

        log.debug("Host %s: Uptime %s", self.host, self._uptime)
        return self._uptime

    @property
    def uptime_string(self):
        """
        Get uptime of the device in the format of dd::hh::mm.

        Returns:
            str: Uptime in string format.
        """
        if self._uptime_string is None:
            self._uptime_string = self._uptime_to_string(self.uptime)

        return self._uptime_string

    @property
    def hostname(self):
        """Get hostname from device.

        Returns:
            str: Hostname of the device.
        """
        if self._hostname is None:
            sh_hostname_output = self.show("show hostname")
            self._hostname = sh_hostname_output["hostname"]

        log.debug("Host %s: Hostname %s", self.host, self._hostname)
        return self._hostname

    @property
    def interfaces(self):
        """Get list of interfaces on device.

        Returns:
            list: List of interfaces
        """
        if self._interfaces is None:
            iface_detailed_list = self._interfaces_status_list()
            self._interfaces = sorted(list(x["interface"] for x in iface_detailed_list))

        log.debug("Host %s: Interfaces %s", self.host, self._interfaces)
        return self._interfaces

    @property
    def vlans(self):
        """Get list of VLANS on device.

        Returns:
            list: List of VLANS on device.
        """
        if self._vlans is None:
            vlans = EOSVlans(self)
            self._vlans = vlans.get_list()

        log.debug("Host %s: Vlans %s", self.host, self._vlans)
        return self._vlans

    @property
    def fqdn(self):
        """Get fully-qualified domain name of device.

        Returns:
            str: Fully-qualified domain name of device.
        """
        if self._fqdn is None:
            sh_hostname_output = self.show("show hostname")
            self._fqdn = sh_hostname_output["fqdn"]

        log.debug("Host %s: FQDN %s", self.host, self._fqdn)
        return self._fqdn

    @property
    def model(self):
        """Get model of device.

        Returns:
            str: Model of device.
        """
        if self._model is None:
            sh_version_output = self.show("show version")
            self._model = sh_version_output["modelName"]

        log.debug("Host %s: Model %s", self.host, self._model)
        return self._model

    @property
    def os_version(self):
        """Get OS version on device.

        Returns:
            str: OS version of device.
        """
        if self._os_version is None:
            sh_version_output = self.show("show version")
            self._os_version = sh_version_output["internalVersion"]

        log.debug("Host %s: OS version %s", self.host, self._os_version)
        return self._os_version

    @property
    def serial_number(self):
        """Get serial number of device.

        Returns:
            str: Serial number of device.
        """
        if self._serial_number is None:
            sh_version_output = self.show("show version")
            self._serial_number = sh_version_output["serialNumber"]

        log.debug("Host %s: Serial number %s", self.host, self._serial_number)
        return self._serial_number

    def file_copy(self, src, dest=None, file_system=None):
        """Copy file to device.

        Args:
            src (string): source file
            dest (string, optional): Destintion file. Defaults to None.
            file_system (string, optional): Describes device file system. Defaults to None.

        Raises:
            FileTransferError: raise exception if there is an error
        """
        self.open()
        self.enable()

        if file_system is None:
            file_system = self._get_file_system()

        if not self.file_copy_remote_exists(src, dest, file_system):
            file_copy = self._file_copy_instance(src, dest, file_system=file_system)

            try:
                file_copy.enable_scp()
                file_copy.establish_scp_conn()
                file_copy.transfer_file()
                log.info("Host %s: File %s transferred successfully.", self.host, src)
            except:  # noqa E722
                log.error("Host %s: File transfer error %s", self.host, FileTransferError.default_message)
                raise FileTransferError
            finally:
                file_copy.close_scp_chan()

            if not self.file_copy_remote_exists(src, dest, file_system):
                log.error(
                    "Host %s: Attempted file copy, but could not validate file existed after transfer %s",
                    self.host,
                    FileTransferError.default_message,
                )
                raise FileTransferError

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, file_system=None):
        """Copy file to remote device if it exists.

        Args:
            src (string): source file
            dest (string, optional): Destintion file. Defaults to None.
            file_system (string, optional): Describes device file system. Defaults to None.

        Returns:
            bool: True if remote file exists.
        """
        self.enable()
        if file_system is None:
            file_system = self._get_file_system()

        filecopy = self._file_copy_instance(src, dest, file_system=file_system)
        if filecopy.check_file_exists() and filecopy.compare_md5():
            log.debug("Host %s: File %s already exists on remote.", self.host, src)
            return True

        log.debug("Host %s: File %s does not already exist on remote.", self.host, src)
        return False

    def install_os(self, image_name, **vendor_specifics):
        """Install new OS on device.

        Args:
            image_name (str): Name of the image name to be installed.

        Raises:
            OSInstallError: Error in installing new OS.

        Returns:
            bool: True if device OS is succesfully installed.
        """
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            self.set_boot_options(image_name, **vendor_specifics)
            self.reboot()
            self._wait_for_device_reboot(timeout=timeout)
            if not self._image_booted(image_name):
                log.error("Host %s: OS install error for image %s", self.host, image_name)
                raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

            log.info("Host %s: OS image %s installed successfully.", self.host, image_name)
            return True

        log.info("Host %s: OS image %s not installed.", self.host, image_name)
        return False

    def open(self):
        """Open ssh connection with Netmiko ConnectHandler to be used with FileTransfer."""
        if self._connected:
            try:
                self.native_ssh.find_prompt()  # pylint: disable=access-member-before-definition
            except Exception:  # pylint: disable=broad-except
                self._connected = False

        if not self._connected:
            self.native_ssh = ConnectHandler(  # pylint: disable=attribute-defined-outside-init
                device_type="arista_eos",
                ip=self.host,
                username=self.username,
                password=self.password,
                # port=self.port,
                # global_delay_factor=self.global_delay_factor,
                # secret=self.secret,
                verbose=False,
            )
            self._connected = True

        log.debug("Host %s: Connection to controller was opened successfully.", self.host)

    def reboot(self, wait_for_reload=False, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            wait_for_reload: Whether or not reboot method should also run _wait_for_device_reboot(). Defaults to False.

        Raises:
            RebootTimeoutError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = EOSDevice(**connection_args)
            >>> device.reboot()
            >>>

        """
        if kwargs.get("confirm"):
            log.warning("Passing 'confirm' to reboot method is deprecated.")

        self.show("reload now")
        log.info("Host %s: Device rebooted.", self.host)
        if wait_for_reload:
            self._wait_for_device_reboot()

    def rollback(self, rollback_to):
        """Rollback device configuration.

        Args:
            rollback_to (str): Name of file to revert configuration to.

        Raises:
            RollbackError: When rollback is unsuccessful.
        """
        try:
            self.show(f"configure replace {rollback_to} force")
            log.info("Host %s: Rollback to %s.", self.host, rollback_to)
        except (CommandError, CommandListError):
            log.error("Host %s: Rollback unsuccessful. %s may not exist.", self.host, rollback_to)
            raise RollbackError(f"Rollback unsuccessful. {rollback_to} may not exist.")

    @property
    def running_config(self):
        """Return running config.

        Returns:
            str: Running configuration.
        """
        log.debug("Host %s: Show running config.", self.host)
        return self.show("show running-config", raw_text=True)

    def save(self, filename="startup-config"):
        """Show running configuration.

        Returns:
            str: Running configuration.
        """
        log.debug("Host %s: Copy running config with name %s.", self.host, filename)
        self.show(f"copy running-config {filename}")
        return True

    def set_boot_options(self, image_name, **vendor_specifics):
        """Set boot option to specified image.

        Args:
            image_name (str): Name of the image file.

        Raises:
            NTCFileNotFoundError: File not found on device.
            CommandError: Error in trying to set image as boot option.
        """
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = self._get_file_system()

        file_system_files = self.show(f"dir {file_system}", raw_text=True)
        if re.search(image_name, file_system_files) is None:
            log.error("Host %s: File not found error for image %s.", self.host, image_name)
            raise NTCFileNotFoundError(hostname=self.hostname, file=image_name, directory=file_system)

        self.show(f"install source {file_system}{image_name}")
        if self.boot_options["sys"] != image_name:
            log.error("Host %s: Setting boot command did not yield expected results", self.host)
            raise CommandError(
                command=f"install source {image_name}",
                message="Setting install source did not yield expected results",
            )

        log.info("Host %s: boot options have been set to %s", self.host, image_name)

    def show(self, commands, raw_text=False):
        """Send configuration commands to a device.

        Args:
            commands (str, list): String with single command, or list with multiple commands.
            raw_text (bool, optional): False if encode should be json, True if encoding is text. Defaults to False.

        Raises:
            CommandError: Issue with the command provided.
            CommandListError: Issue with a command in the list provided.
        """
        if not raw_text:
            encoding = "json"
        else:
            encoding = "text"

        original_commands_is_str = isinstance(commands, str)
        if original_commands_is_str:
            commands = [commands]
        try:
            response = self.native.enable(commands, encoding=encoding)
            response_list = self._parse_response(response, raw_text=raw_text)
            if original_commands_is_str:
                return response_list[0]
            log.debug("Host %s: Successfully executed command 'show' with responses %s.", self.host, response_list)
            return response_list
        except EOSCommandError as err:
            if original_commands_is_str:
                log.error("Host %s: Command error for command %s with message %s.", self.host, commands, err.message)
                raise CommandError(err.commands, err.message)
            log.error("Host %s: Command list error for commands %s with message %s.", self.host, commands, err.message)
            raise CommandListError(commands, err.commands[len(err.commands) - 1], err.message)

    @property
    def startup_config(self):
        """Get startup configuration.

        Returns:
            str: Startup configuration.
        """
        log.debug("Host %s: show startup-config", self.host)
        return self.show("show startup-config", raw_text=True)


class RebootSignal(NTCError):
    """Error for sending reboot signal."""

    pass  # pylint: disable=unnecessary-pass
