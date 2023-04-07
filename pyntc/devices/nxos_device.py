"""Module for using an NXOS device over NX-API."""
import os
import re
import time

from pynxos.device import Device as NXOSNative
from pynxos.errors import CLIError
from pynxos.features.file_copy import FileTransferError as NXOSFileTransferError

from requests.exceptions import ReadTimeout

from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs, RollbackError
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileTransferError,
    NTCFileNotFoundError,
    OSInstallError,
    RebootTimeoutError,
)


@fix_docs
class NXOSDevice(BaseDevice):
    """Cisco NXOS Device Implementation."""

    vendor = "cisco"

    def __init__(self, host, username, password, transport="http", timeout=30, port=None, **kwargs):  # noqa: D403
        """PyNTC Device implementation for Cisco IOS.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            transport (str, optional): Transport protocol to connect to device. Defaults to "http".
            timeout (int, optional): Timeout in seconds. Defaults to 30.
            port (int, optional): Port used to connect to device. Defaults to None.
        """
        super().__init__(host, username, password, device_type="cisco_nxos_nxapi")
        self.transport = transport
        self.timeout = timeout
        self.native = NXOSNative(host, username, password, transport=transport, timeout=timeout, port=port, **kwargs)
        log.init(host=host)

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show version", raw_text=True)
        if re.search(image_name, version_data):
            log.info("Host %s: Image %s booted successfully.", self.host, image_name)
            return True

        log.info("Host %s: Image %s not booted successfully.", self.host, image_name)
        return False

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.native.show("show hostname")
                log.debug("Host %s: Device rebooted.", self.host)
                return
            except:  # noqa E722 # nosec  # pylint: disable=bare-except
                pass

        log.error("Host %s: Device timed out while rebooting.", self.host)
        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        """Backup running configuration.

        Args:
            filename (str): Name of backup file.
        """
        self.native.backup_running_config(filename)
        log.debug("Host %s: Running config backed up.", self.host)

    @property
    def boot_options(self):
        """Get current boot variables.

        Returns:
            dict: e.g . {"kick": "router_kick.img", "sys": "router_sys.img"}
        """
        boot_options = self.native.get_boot_options()
        log.debug("Host %s: the boot options are %s", self.host, boot_options)
        return boot_options

    def checkpoint(self, filename):
        """Save a checkpoint of the running configuration to the device.

        Args:
            filename (str): The filename to save the checkpoint on the remote device.
        """
        log.debug("Host %s: checkpoint is %s.", self.host, filename)
        return self.native.checkpoint(filename)

    def close(self):  # noqa: D401
        """Implements ``pass``."""
        pass  # pylint: disable=unnecessary-pass

    def config(self, command):
        """Send configuration command.

        Args:
            command (str, list): command to be sent to the device.

        Raises:
            CommandError: Error if command is not succesfully ran on device.
        """
        if isinstance(command, list):
            try:
                self.native.config_list(command)
                log.info("Host %s: Configured with commands: %s", self.host, command)
            except CLIError as e:
                log.error("Host %s: Command error with commands: %s and error message %s", self.host, command, str(e))
                raise CommandListError(command, e.command, str(e))
        else:
            try:
                self.native.config(command)
                log.info("Host %s: Device configured with command %s.", self.host, command)
            except CLIError as e:
                log.error("Host %s: Command error with commands: %s and error message %s", self.host, command, str(e))
                raise CommandError(command, str(e))

    @property
    def uptime(self):
        """Get uptime of the device in seconds.

        Returns:
            int: Uptime of the device in seconds.
        """
        if self._uptime is None:
            self._uptime = self.native.facts.get("uptime")

        log.debug("Host %s: Uptime %s", self.host, self._uptime)
        return self._uptime

    @property
    def hostname(self):
        """Get hostname of the device.

        Returns:
            str: Hostname of the device.
        """
        if self._hostname is None:
            self._hostname = self.native.facts.get("hostname")

        log.debug("Host %s: Hostname %s", self.host, self._hostname)
        return self._hostname

    @property
    def interfaces(self):
        """Get list of interfaces.

        Returns:
            list: List of interfaces.
        """
        if self._interfaces is None:
            self._interfaces = self.native.facts.get("interfaces")

        log.debug("Host %s: Interfaces %s", self.host, self._interfaces)
        return self._interfaces

    @property
    def vlans(self):
        """Get list of vlans.

        Returns:
            list: List of vlans on the device.
        """
        if self._vlans is None:
            self._vlans = self.native.facts.get("vlans")

        log.debug("Host %s: Vlans %s", self.host, self._vlans)
        return self._vlans

    @property
    def fqdn(self):
        """Get fully qualified domain name.

        Returns:
            str: Fully qualified domain name.
        """
        if self._fqdn is None:
            self._fqdn = self.native.facts.get("fqdn")

        log.debug("Host %s: FQDN %s", self.host, self._fqdn)
        return self._fqdn

    @property
    def model(self):
        """Get device model.

        Returns:
            str: Model of device.
        """
        if self._model is None:
            self._model = self.native.facts.get("model")

        log.debug("Host %s: Model %s", self.host, self._model)
        return self._model

    @property
    def os_version(self):
        """Get device version.

        Returns:
            str: Device version.
        """
        if self._os_version is None:
            self._os_version = self.native.facts.get("os_version")

        log.debug("Host %s: OS version %s", self.host, self._os_version)
        return self._os_version

    @property
    def serial_number(self):
        """Get device serial number.

        Returns:
            str: Device serial number.
        """
        if self._serial_number is None:
            self._serial_number = self.native.facts.get("serial_number")

        log.debug("Host %s: Serial number %s", self.host, self._serial_number)
        return self._serial_number

    def file_copy(self, src, dest=None, file_system="bootflash:"):
        """Send a local file to the device.

        Args:
            src (str): Path to the local file to send.
            dest (str, optional): The destination file path. Defaults to basename of source path.
            file_system (str, optional): [The file system for the remote file. Defaults to "bootflash:".

        Raises:
            FileTransferError: Error if transfer of file cannot be verified.
        """
        if not self.file_copy_remote_exists(src, dest, file_system):
            dest = dest or os.path.basename(src)
            try:
                file_copy = self.native.file_copy(
                    src, dest, file_system=file_system
                )  # pylint: disable=assignment-from-no-return
                log.info("Host %s: File %s transferred successfully.", self.host, src)
                if not self.file_copy_remote_exists(src, dest, file_system):
                    log.error(
                        "Host %s: Attempted file copy, but could not validate file existed after transfer %s",
                        self.host,
                        FileTransferError.default_message,
                    )
                    raise FileTransferError
                return file_copy

            except NXOSFileTransferError as err:
                log.error("Host %s: NXOS file transfer error %s", self.host, str(err))
                raise FileTransferError

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, file_system="bootflash:"):
        """Check if a remote file exists.

        Args:
            src (str): Path to the local file to send.
            dest (str, optional): The destination file path to be saved on remote device. Defaults to basename of source path.
            file_system (str, optional): The file system for the remote file. Defaults to "bootflash:".

        Returns:
            bool: True if the remote file exists. Otherwise, false.
        """
        dest = dest or os.path.basename(src)
        log.debug(
            "Host %s: File %s exists on remote %s.",
            self.host,
            src,
            self.native.file_copy_remote_exists(src, dest, file_system=file_system),
        )
        return self.native.file_copy_remote_exists(src, dest, file_system=file_system)

    def install_os(self, image_name, **vendor_specifics):
        """Upgrade device with provided image.

        Args:
            image_name (str): Name of the image file to upgrade the device to.

        Raises:
            OSInstallError: Error if boot option is not set to new image.

        Returns:
            bool: True if new image is boot option on device. Otherwise, false.
        """
        self.native.show("terminal dont-ask")
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            self.set_boot_options(image_name, **vendor_specifics)
            self._wait_for_device_reboot(timeout=timeout)
            if not self._image_booted(image_name):
                log.error("Host %s: OS install error for image %s", self.host, image_name)
                raise OSInstallError(hostname=self.facts.get("hostname"), desired_boot=image_name)
            self.save()

            log.info("Host %s: OS image %s installed successfully.", self.host, image_name)
            return True

        log.info("Host %s: OS image %s not installed.", self.host, image_name)
        return False

    def open(self):  # noqa: D401
        """Implements ``pass``."""
        pass  # pylint: disable=unnecessary-pass

    def reboot(self, wait_for_reload=False, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            wait_for_reload: Whether or not reboot method should also run _wait_for_device_reboot(). Defaults to False.

        Raises:
            RebootTimerError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = NXOSDevice(**connection_args)
            >>> device.reboot()
            >>
        """
        if kwargs.get("confirm"):
            log.warning("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)
        try:
            self.native.show_list(["terminal dont-ask", "reload"])
            # The native reboot is not always properly disabling confirmation. Above is more consistent.
            # self.native.reboot(confirm=True)
        except ReadTimeout as expected_exception:
            log.info("Host %s: Device rebooted.", self.host)
            log.info("Hit expected exception during reload: %s", expected_exception.__class__)
        if wait_for_reload:
            time.sleep(10)
            self._wait_for_device_reboot()
        log.info("Host %s: Device rebooted.", self.host)

    def rollback(self, filename):
        """Rollback configuration to specified file.

        Args:
            filename (str): Name of the file to rollback to.

        Raises:
            RollbackError: Error if rollback command is unsuccesfull.
        """
        try:
            self.native.rollback(filename)
            log.info("Host %s: Rollback to %s.", self.host, filename)
        except CLIError:
            log.error("Host %s: Rollback unsuccessful. %s may not exist.", self.host, filename)
            raise RollbackError(f"Rollback unsuccessful, {filename} may not exist.")

    @property
    def running_config(self):
        """Get running configuration of device.

        Returns:
            str: Running configuration of device.
        """
        log.debug("Host %s: Show running config.", self.host)
        return self.native.running_config

    def save(self, filename="startup-config"):
        """Save a device's running configuration.

        Args:
            filename (str, optional): Filename to save running configuration to. Defaults to "startup-config".

        Returns:
            bool: True if configuration is saved.
        """
        log.debug("Host %s: Copy running config with name %s.", self.host, filename)
        return self.native.save(filename=filename)

    def set_boot_options(self, image_name, kickstart=None, **vendor_specifics):
        """Set boot variables.

        Args:
            image_name (str): Main system image file.
            kickstart (str, optional): Kickstart filename. Defaults to None.

        Raises:
            NTCFileNotFoundError: Error if either image_name or kickstart image not found on device.
        """
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = "bootflash:"

        file_system_files = self.show(f"dir {file_system}", raw_text=True)
        if re.search(image_name, file_system_files) is None:
            log.error("Host %s: File not found error for image %s.", self.host, image_name)
            raise NTCFileNotFoundError(hostname=self.hostname, file=image_name, directory=file_system)

        if kickstart is not None:
            if re.search(kickstart, file_system_files) is None:
                log.error("Host %s: File not found error for image %s.", self.host, image_name)
                raise NTCFileNotFoundError(hostname=self.hostname, file=kickstart, directory=file_system)

            kickstart = file_system + kickstart

        image_name = file_system + image_name
        # Allow for user defined timeout to take precedence if its over 300 seconds, otherwise change to 300.
        try:
            native_timeout = int(self.native.timeout)
        except (TypeError, ValueError):
            native_timeout = 1

        if native_timeout < 300:
            self.native.timeout = 300
        upgrade_result = self.native.set_boot_options(
            image_name, kickstart=kickstart
        )  # pylint: disable=assignment-from-no-return
        self.native.timeout = 30

        log.info("Host %s: boot options have been set to %s", self.host, upgrade_result)
        return upgrade_result

    def set_timeout(self, timeout):
        """Set timeout value on device connection.

        Args:
            timeout (int): Timeout value.
        """
        log.debug("Host %s: Timeout set to %s.", self.host, timeout)
        self.native.timeout = timeout

    def show(self, command, raw_text=False):
        """Send a non-configuration command.

        Args:
            command (str): The command to send to the device.
            raw_text (bool, optional): Whether to return raw text or structured data. Defaults to False.

        Raises:
            CommandError: Error message stating which command failed.

        Returns:
            str: Results of the command ran.
        """
        log.debug("Host %s: Successfully executed command 'show' with responses.", self.host)
        if isinstance(command, list):
            try:
                log.debug("Host %s: Successfully executed command 'show' with commands %s.", self.host, command)
                return self.native.show_list(command, raw_text=raw_text)
            except CLIError as e:
                log.error("Host %s: Command error for command %s with message %s.", self.host, e.command, str(e))
                raise CommandListError(command, e.command, str(e))
        try:
            log.debug("Host %s: Successfully executed command 'show'.", self.host)
            return self.native.show(command, raw_text=raw_text)
        except CLIError as e:
            log.error("Host %s: Command error %s.", self.host, str(e))
            raise CommandError(command, str(e))

    @property
    def startup_config(self):
        """Get startup configuration.

        Returns:
            str: Startup configuration.
        """
        return self.show("show startup-config", raw_text=True)
