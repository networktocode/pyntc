"""Module for using a Juniper junOS device."""
import hashlib
import os
import re
import time
import warnings
from tempfile import NamedTemporaryFile

from jnpr.junos import Device as JunosNativeDevice
from jnpr.junos.exception import ConfigLoadError
from jnpr.junos.op.ethport import EthPortTable
from jnpr.junos.utils.config import Config as JunosNativeConfig
from jnpr.junos.utils.fs import FS as JunosNativeFS
from jnpr.junos.utils.scp import SCP
from jnpr.junos.utils.sw import SW as JunosNativeSW
from pyntc.errors import CommandError, CommandListError, FileTransferError, RebootTimeoutError

from .base_device import BaseDevice, fix_docs
from .tables.jnpr.loopback import LoopbackTable


@fix_docs
class JunosDevice(BaseDevice):
    """Juniper JunOS Device Implementation."""

    vendor = "juniper"

    def __init__(self, host, username, password, *args, **kwargs):  # noqa: D403
        """PyNTC device implementation for Juniper JunOS.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
        """
        super().__init__(host, username, password, *args, device_type="juniper_junos_netconf", **kwargs)

        self.native = JunosNativeDevice(*args, host=host, user=username, passwd=password, **kwargs)
        self.open()
        self.cu = JunosNativeConfig(self.native)
        self.fs = JunosNativeFS(self.native)
        self.sw = JunosNativeSW(self.native)

    def _file_copy_local_file_exists(self, filepath):
        return os.path.isfile(filepath)

    def _file_copy_local_md5(self, filepath, blocksize=2**20):
        if self._file_copy_local_file_exists(filepath):
            m = hashlib.md5()  # nosec
            with open(filepath, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    def _file_copy_remote_md5(self, filename):
        return self.fs.checksum(filename)

    def _get_interfaces(self):
        eth_ifaces = EthPortTable(self.native)
        eth_ifaces.get()

        loop_ifaces = LoopbackTable(self.native)
        loop_ifaces.get()

        ifaces = eth_ifaces.keys()
        ifaces.extend(loop_ifaces.keys())

        return ifaces

    def _image_booted(self, image_name, **vendor_specifics):
        raise NotImplementedError

    def _uptime_components(self, uptime_full_string):
        match_days = re.search(r"(\d+) days?", uptime_full_string)
        match_hours = re.search(r"(\d+) hours?", uptime_full_string)
        match_minutes = re.search(r"(\d+) minutes?", uptime_full_string)
        match_seconds = re.search(r"(\d+) seconds?", uptime_full_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0
        seconds = int(match_seconds.group(1)) if match_seconds else 0

        return days, hours, minutes, seconds

    def _uptime_to_seconds(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)

        seconds += days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60

        return seconds

    def _uptime_to_string(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)
        return "%02d:%02d:%02d:%02d" % (days, hours, minutes, seconds)

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                return
            except:  # noqa E722 # nosec
                pass

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        """Backup current running configuration.

        Args:
            filename (str): Name used for backup file.
        """
        with open(filename, "w") as f:
            f.write(self.running_config)

    @property
    def boot_options(self):
        """Get os version on device.

        Returns:
            str: OS version on device.
        """
        return self.os_version

    def checkpoint(self, filename):
        """Create checkpoint file.

        Args:
            filename (str): Name of checkpoint file.
        """
        self.save(filename)

    def close(self):
        """Close connection to device."""
        if self.connected:
            self.native.close()

    def config(self, commands, format="set"):
        """Send configuration commands to a device.

        Args:
             commands (str, list): String with single command, or list with multiple commands.

        Raises:
             ConfigLoadError: Issue with loading the command.
             CommandError: Issue with the command provided, if its a single command, passed in as a string.
             CommandListError: Issue with a command in the list provided.
        """
        if isinstance(commands, str):
            try:
                self.cu.load(commands, format=format)
                self.cu.commit()
            except ConfigLoadError as e:
                raise CommandError(commands, e.message)
        else:
            try:
                for command in commands:
                    self.cu.load(command, format=format)

                self.cu.commit()
            except ConfigLoadError as e:
                raise CommandListError(commands, command, e.message)

    def config_list(self, commands, format="set"):
        """Send configuration commands in list format to a device.

        DEPRECATED - Use the `config` method.

        Args:
            commands (list): List with multiple commands.
            format (str): The Junos format the commands are in.
        """
        warnings.warn("config_list() is deprecated; use config().", DeprecationWarning)
        self.config(commands, format=format)

    @property
    def connected(self):
        """Get connection status of device.

        Returns:
            bool: True if connection is active. Otherwise, false.
        """
        return self.native.connected

    @property
    def uptime(self):
        """Get device uptime in seconds.

        Returns:
            int: Device uptime in seconds.
        """
        try:
            native_uptime_string = self.native.facts["RE0"]["up_time"]
        except (AttributeError, TypeError):
            native_uptime_string = None

        if self._uptime is None:
            if native_uptime_string is not None:
                self._uptime = self._uptime_to_seconds(native_uptime_string)

        return self._uptime

    @property
    def uptime_string(self):
        """
        Get device uptime in format dd:hh:mm:ss.

        Returns:
            str: Device uptime.
        """
        try:
            native_uptime_string = self.native.facts["RE0"]["up_time"]
        except (AttributeError, TypeError):
            native_uptime_string = None

        if self._uptime_string is None:
            self._uptime_string = self._uptime_to_string(native_uptime_string)

        return self._uptime_string

    @property
    def hostname(self):
        """Get device hostname.

        Returns:
            str: Device hostname.
        """
        if self._hostname is None:
            self._hostname = self.native.facts.get("hostname")

        return self._hostname

    @property
    def interfaces(self):
        """Get list of interfaces.

        Returns:
            list: List of interfaces.
        """
        if self._interfaces is None:
            self._interfaces = self._get_interfaces()

        return self._interfaces

    @property
    def fqdn(self):
        """Get fully qualified domain name.

        Returns:
            str: Fully qualified domain name.
        """
        if self._fqdn is None:
            self._fqdn = self.native.facts.get("fqdn")

        return self._fqdn

    @property
    def model(self):
        """Get device model.

        Returns:
            str: Device model.
        """
        if self._model is None:
            self._model = self.native.facts.get("model")

        return self._model

    @property
    def os_version(self):
        """Get OS version.

        Returns:
            str: OS version.
        """
        if self._os_version is None:
            self._os_version = self.native.facts.get("version")

        return self._os_version

    @property
    def serial_number(self):
        """Get serial number.

        Returns:
            str: Serial number.
        """
        if self._serial_number is None:
            self._serial_number = self.native.facts.get("serialnumber")

        return self._serial_number

    def file_copy(self, src, dest=None, **kwargs):
        """Copy file to device via SCP.

        Args:
            src (str): Name of file to be transferred.
            dest (str, optional): Path on device to save file. Defaults to None.

        Raises:
            FileTransferError: Raised when unable to verify file was transferred succesfully.
        """
        if not self.file_copy_remote_exists(src, dest, **kwargs):
            if dest is None:
                dest = os.path.basename(src)

            with SCP(self.native) as scp:
                scp.put(src, remote_path=dest)

            if not self.file_copy_remote_exists(src, dest, **kwargs):
                raise FileTransferError(
                    message="Attempted file copy, but could not validate file existed after transfer"
                )

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        """Verify device already has existing file.

        Args:
            src (str): Source of local file.
            dest (str, optional): Path of file on device. Defaults to None.

        Returns:
            bool: True if hashes of the file match. Otherwise, false.
        """
        if dest is None:
            dest = os.path.basename(src)

        local_hash = self._file_copy_local_md5(src)
        remote_hash = self._file_copy_remote_md5(dest)
        if local_hash is not None and local_hash == remote_hash:
            return True
        return False

    def install_os(self, image_name, **vendor_specifics):
        """Install OS on device.

        Args:
            image_name (str): Name of image.

        Raises:
            NotImplementedError: Method currently not implemented.
        """
        raise NotImplementedError

    def open(self):
        """Open connection to device."""
        if not self.connected:
            self.native.open()

    def reboot(self, timer=0, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            timer (int, optional): The time to wait before reloading. Defaults to 0.

        Example:
            >>> device = JunosDevice(**connection_args)
            >>> device.reboot()
            >>>
        """
        if kwargs.get("confirm"):
            warnings.warn("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        self.sw = JunosNativeSW(self.native)
        self.sw.reboot(in_min=timer)

    def rollback(self, filename):
        """Rollback to a specific configuration file.

        Args:
            filename (str): Filename to rollback device to.
        """
        self.native.timeout = 60

        temp_file = NamedTemporaryFile()

        with SCP(self.native) as scp:
            scp.get(filename, local_path=temp_file.name)

        self.cu.load(path=temp_file.name, format="text", overwrite=True)
        self.cu.commit()

        temp_file.close()

        self.native.timeout = 30

    @property
    def running_config(self):
        """Get running configuration.

        Returns:
            str: Running configuration.
        """
        return self.show("show config")

    def save(self, filename=None):
        """
        Save current configuration to device.

        If filename is provided, save current configuration to file.

        Args:
            filename (str, optional): Filename to save current configuration. Defaults to None.

        Returns:
            bool: True if new file created for save file. Otherwise, just returns if save is to default name.
        """
        if filename is None:
            self.cu.commit()
            return

        temp_file = NamedTemporaryFile()
        temp_file.write(self.show("show config"))
        temp_file.flush()

        with SCP(self.native) as scp:
            scp.put(temp_file.name, remote_path=filename)

        temp_file.close()
        return True

    def set_boot_options(self, sys):
        """Set boot options.

        Args:
            sys (str): Name of image to set boot option to.

        Raises:
            NotImplementedError: Method currently not implemented.
        """
        raise NotImplementedError

    def show(self, commands):
        """Send configuration commands to a device.

        Args:
            commands (str, list): String with single command, or list with multiple commands.

        Raises:
            CommandError: Issue with the command provided.
            CommandListError: Issue with a command in the list provided.
        """
        original_commands_is_str = isinstance(commands, str)
        if original_commands_is_str:
            commands = [commands]
        responses = []
        for command in commands:
            if not command.startswith("show"):
                if original_commands_is_str:
                    raise CommandError(command, 'Juniper "show" commands must begin with "show".')
                raise CommandListError(commands, command, 'Juniper "show" commands must begin with "show".')

            response = self.native.cli(command, warning=False)
            responses.append(response)
        if original_commands_is_str:
            return responses[0]
        return responses

    def show_list(self, commands, raw_text=True):
        """Send show commands in list format to a device.

        DEPRECATED - Use the `show` method.

        Args:
            commands (list): List with multiple commands.
            raw_text (bool): Return raw text or structured text.
        """
        warnings.warn("show_list() is deprecated; use show().", DeprecationWarning)
        return self.show(commands)

    @property
    def startup_config(self):
        """Get startup configuration.

        Returns:
            str: Startup configuration.
        """
        return self.show("show config")
