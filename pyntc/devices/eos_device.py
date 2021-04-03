"""Module for using an Arista EOS device over the eAPI."""

import re
import time
import os
import warnings

from pyeapi import connect as eos_connect
from pyeapi.client import Node as EOSNative
from pyeapi.eapilib import CommandError as EOSCommandError
from netmiko import ConnectHandler
from netmiko import FileTransfer

from pyntc.utils import convert_list_by_key
from .system_features.vlans.eos_vlans import EOSVlans
from .base_device import BaseDevice, RollbackError, RebootTimerError, fix_docs
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


BASIC_FACTS_KM = {"model": "modelName",
                  "os_version": "internalVersion", "serial_number": "serialNumber"}
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

        fc = FileTransfer(self.native_ssh, src, dest, file_system=file_system)
        log.debug(f"Host {self.host}: File copy instance {fc}.")
        return fc

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
            log.error(f"Host {self.host}: Attribute error with command 'dir'.")
            raise FileSystemNotFoundError(hostname=self.hostname, command="dir")

        log.debug(f"Host {self.host}: File system {file_system}.")
        return file_system

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show boot", raw_text=True)
        if re.search(image_name, version_data):
            log.info(
                f"Host {self.host}: Image {image_name} booted successfully.")
            return True

        return False

    def _interfaces_status_list(self):
        interfaces_list = []
        interfaces_status_dictionary = self.show("show interfaces status")[
            "interfaceStatuses"]
        for key in interfaces_status_dictionary:
            interface_dictionary = interfaces_status_dictionary[key]
            interface_dictionary["interface"] = key
            interfaces_list.append(interface_dictionary)

        interface_status_list = convert_list_by_key(
            interfaces_list, INTERFACES_KM, fill_in=True, whitelist=["interface"]
        )
        log.debug(
            f"Host {self.host}: interfaces detailed list {interface_status_list}.")
        return interface_status_list

    def _parse_response(self, response, raw_text):
        if raw_text:
            return list(x["result"]["output"] for x in response)
        else:
            return list(x["result"] for x in response)

    def _uptime_to_string(self, uptime):
        days = uptime / (24 * 60 * 60)
        uptime = uptime % (24 * 60 * 60)

        hours = uptime / (60 * 60)
        uptime = uptime % (60 * 60)

        mins = uptime / 60
        uptime = uptime % 60

        seconds = uptime

        return "%02d:%02d:%02d:%02d" % (days, hours, mins, seconds)

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.show("show hostname")
                log.debug(f"Host {self.host}: Device rebooted.")
                return
            except:  # noqa E722 # nosec
                pass

        log.error(f"Host {self.host}: Device timed out while rebooting.")
        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        """
        Create backup file of running configuration.

        Args:
            filename (str): The name of the file that will be saved.
        """
        with open(filename, "w") as f:
            f.write(self.running_config)

        log.debug(
            f"Host {self.host}: Running config backed up to {self.running_config}.")

    @property
    def boot_options(self):
        """Get current running software.

        Returns:
            dict: Key is ``sys`` with value being the image on the device.
        """
        image = self.show("show boot-config")["softwareImage"]
        image = image.replace("flash:", "")
        log.debug(f"Host {self.host}: the boot options are {dict(sys=image)}")
        return dict(sys=image)

    def checkpoint(self, checkpoint_file):
        log.debug(f"Host {self.host}: checkpoint is {checkpoint_file}.")
        self.show("copy running-config %s" % checkpoint_file)

    def close(self):
        """Create a checkpoint file of the running config.

        Args:
            checkpoint_file (str): Name of the checkpoint file.
        """
        log.info(f"Host {self.host}: Device configured with command {command}.")
        self.show("copy running-config %s" % checkpoint_file)

    def close(self):
        """Not implemented. Just ``passes``."""
        pass

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
            log.info(
                f"Host {self.host}: Device configured with commands {commands}.")
        except EOSCommandError as e:
            if isinstance(commands, str):
                log.error(
                    f"Host {self.host}: Command error with commands: {commands} and error message {e.message}")
                raise CommandError(commands, e.message)
            raise CommandListError(
                commands, e.commands[len(e.commands) - 1], e.message)

    def config_list(self, commands):
        """Send configuration commands in list format to a device.

        DEPRECATED - Use the `config` method.

        Args:
            commands (list): List with multiple commands.
        """
        log.warning("config_list() is deprecated; use config().",
                    DeprecationWarning)
        self.config(commands)

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

        log.debug(f"Host {self.host}: Device enabled")

    @property
    def uptime(self):
        """
        Get uptime of the device in seconds.

        Returns:
            int: Uptime of the device.
        """
        if self._uptime is None:
            sh_version_output = self.show("show version")
            self._uptime = int(
                time.time() - sh_version_output["bootupTimestamp"])

        log.debug(f"Host {self.host}: Uptime {self._uptime}")
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

        log.debug(f"Host {self.host}: Hostname {self._hostname}")
        return self._hostname

    @property
    def interfaces(self):
        """Get list of interfaces on device.

        Returns:
            list: List of interfaces
        """
        if self._interfaces is None:
            iface_detailed_list = self._interfaces_status_list()
            self._interfaces = sorted(
                list(x["interface"] for x in iface_detailed_list))

        log.debug(f"Host {self.host}: Interfaces {self._interfaces}")
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

        log.debug(f"Host {self.host}: Vlans {self._vlans}")
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

        log.debug(f"Host {self.host}: FQDN {self._fqdn}")
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

        log.debug(f"Host {self.host}: Model {self._model}")
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

        log.debug(f"Host {self.host}: OS version {self._os_version}")
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

        log.debug(f"Host {self.host}: Serial number {self._serial_number}")
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
            fc = self._file_copy_instance(src, dest, file_system=file_system)

            try:
                fc.enable_scp()
                fc.establish_scp_conn()
                fc.transfer_file()
                log.info(
                    f"Host {self.host}: File {src} transferred successfully.")
            except:  # noqa E722
                log.error(
                    f"Host {self.host}: File transfer error {FileTransferError.default_message}")
                raise FileTransferError
            finally:
                fc.close_scp_chan()

            if not self.file_copy_remote_exists(src, dest, file_system):
                log.error(
                    f"Host {self.host}: Attempted file copy, but could not validate file existed after transfer {FileTransferError.default_message}"
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

        fc = self._file_copy_instance(src, dest, file_system=file_system)
        if fc.check_file_exists() and fc.compare_md5():
            log.debug(f"Host {self.host}: File {src} already exists on remote.")
            return True

        log.debug(
            f"Host {self.host}: File {src} does not already exist on remote.")
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
                log.error(
                    f"Host {self.host}: OS install error for image {image_name}")
                raise OSInstallError(hostname=self.hostname,
                                     desired_boot=image_name)

            log.info(
                f"Host {self.host}: OS image {image_name} installed successfully.")
            return True

        log.info(f"Host {self.host}: OS image {image_name} not installed.")
        return False

    def open(self):
        """Open ssh connection with Netmiko ConnectHandler to be used with FileTransfer."""
        if self._connected:
            try:
                self.native_ssh.find_prompt()
            except Exception:
                self._connected = False

        if not self._connected:
            self.native_ssh = ConnectHandler(
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

        log.debug(
            f"Host {self.host}: Connection to controller was opened successfully.")

    def reboot(self, timer=0, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            timer (int, optional): The time to wait before reloading. Defaults to 0.

        Raises:
            RebootTimeoutError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = EOSDevice(**connection_args)
            >>> device.reboot()
            >>>

        """
        if kwargs.get("confirm"):
            log.warning(
                "Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        if timer != 0:
            log.error(f"Host {self.host}: Reboot time error.")
            raise RebootTimerError(self.device_type)

        self.show("reload now")
        log.info(f"Host {self.host}: Device rebooted.")

    def rollback(self, rollback_to):
        """Rollback device configuration.

        Args:
            rollback_to (str): Name of file to revert configuration to.

        Raises:
            RollbackError: When rollback is unsuccesful.
        """
        try:
            self.show("configure replace %s force" % rollback_to)
            log.info(f"Host {self.host}: Rollback to {rollback_to}.")
        except (CommandError, CommandListError):
            log.error(
                f"Host {self.host}: Rollback unsuccessful. {rollback_to} may not exist.")
            raise RollbackError(
                "Rollback unsuccessful. %s may not exist." % rollback_to)

    @property
    def running_config(self):
        log.debug(f"Host {self.host}: Show running config.")
        return self.show("show running-config", raw_text=True)

    def save(self, filename="startup-config"):
        """Show running configuration.

        Returns:
            str: Running configuration.
        """
        log.debug(
            f"Host {self.host}: Copy running config with name {filename}.")
        return self.show("show running-config", raw_text=True)

    def save(self, filename="startup-config"):
        """Copy running configuration to startup configuration.

        Args:
            filename (str, optional): Name where you want running configuration to save. Defaults to "startup-config".

        Returns:
            bool: True when succesfull.
        """
        self.show("copy running-config %s" % filename)
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

        file_system_files = self.show(
            "dir {0}".format(file_system), raw_text=True)
        if re.search(image_name, file_system_files) is None:
            log.error(
                f"Host {self.host}: File not found error for image {image_name}.")
            raise NTCFileNotFoundError(
                hostname=self.hostname, file=image_name, dir=file_system)

        self.show("install source {0}{1}".format(file_system, image_name))
        if self.boot_options["sys"] != image_name:
            log.error(
                f"Host {self.host}: Setting boot command did not yield expected results")
            raise CommandError(
                command="install source {0}".format(image_name),
                message="Setting install source did not yield expected results",
            )

        log.info(
            f"Host {self.host}: boot options have been set to {image_name}")

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
            log.debug(
                f"Host {self.host}: Successfully executed command 'show' with responses {response_list}.")
            return response_list
        except EOSCommandError as e:
            if original_commands_is_str:
                log.error(
                    f"Host {self.host}: Command error for command {commands} with message {e.message}.")
                raise CommandError(e.commands, e.message)
            log.error(
                f"Host {self.host}: Command list error for commands {commands} with message {e.message}.")
            raise CommandListError(
                commands, e.commands[len(e.commands) - 1], e.message)

    def show_list(self, commands):
        """Send show commands in list format to a device.

        DEPRECATED - Use the `show` method.

        Args:
            commands (list): List with multiple commands.
        """
        log.warning("show_list() is deprecated; use show().",
                    DeprecationWarning)
        self.show(commands)

    @property
    def startup_config(self):
        """Get startup configuration.

        Returns:
            str: Startup configuration.
        """
        log.debug(f"Host {self.host}: show startup-config")
        return self.show("show startup-config", raw_text=True)


class RebootSignal(NTCError):
    """Error for sending reboot signal."""

    pass
