"""Module for using a Cisco WLC/AIREOS device over SSH."""

import os
import re
import time
import signal

from netmiko import ConnectHandler

from .base_device import BaseDevice, fix_docs
from .system_features.file_copy.base_file_copy import FileTransferError
from pyntc.errors import (
    NTCError,
    CommandError,
    OSInstallError,
    CommandListError,
    RebootTimeoutError,
    NTCFileNotFoundError,
)


RE_FILENAME_FIND_VERSION = re.compile(r"^\S+?-[A-Za-z]{2}\d+-(?:\S+-?)?(?:K9-)?(?P<version>\d+-\d+-\d+-\d+)", re.M)


def convert_filename_to_version(filename):
    """
    Extract the aireos version number from image filename.

    Args:
        filename (str): The name of the file downloaded from Cisco.

    Returns:
        str: The version number.

    Example:
        >>> version = convert_filename_to_version("AIR-CT5520-K9-8-8-125-0.aes")
        >>> print(version)
        8.8.125.0
        >>>
    """
    version_match = RE_FILENAME_FIND_VERSION.match(filename)
    version_string = version_match.groupdict()["version"]
    version = version_string.replace("-", ".")
    return version


@fix_docs
class AIREOSDevice(BaseDevice):
    """Cisco AIREOS Device Implementation."""

    vendor = "cisco"

    def __init__(self, host, username, password, secret="", port=22, **kwargs):
        super().__init__(host, username, password, device_type="cisco_aireos_ssh")
        self.native = None
        self.secret = secret
        self.port = int(port)
        self.global_delay_factor = kwargs.get("global_delay_factor", 1)
        self.delay_factor = kwargs.get("delay_factor", 1)
        self._connected = False
        self.open()

    def _enter_config(self):
        """Enter into config mode."""
        self.enable()
        self.native.config_mode()

    def _image_booted(self, image_name, **vendor_specifics):
        """
        Check if ``image_name`` is the currently booted image.

        Args:
            image_name (str): The version to check if image is booted.

        Returns:
            bool: True if ``image_name`` is the current boot version, else False.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device._image_booted("8.10.105.0")
            True
            >>>
        """
        re_version = r"^Product\s+Version\s*\.+\s*(\S+)"
        sysinfo = self.show("show sysinfo")
        booted_image = re.search(re_version, sysinfo, re.M)
        if booted_image.group(1) == image_name:
            return True

        return False

    def _send_command(self, command, expect=False, expect_string=""):
        """
        Send single command to device.

        Args:
            command (str): The command to send to the device.
            expect (bool): Whether to send a different expect string than normal prompt.
            expect_string (str): The expected prompt after running the command.

        Returns:
            str: The response from the device after issuing the ``command``.

        Raises:
            CommandError: When the returned data indicates the command failed.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> sysinfo = device._send_command("show sysinfo")
            >>> print(sysinfo)
            Product Version.....8.2.170.0
            System Up Time......3 days 2 hrs 20 mins 30 sec
            ...
            >>>
        """
        if expect:
            if expect_string:
                response = self.native.send_command_expect(command, expect_string=expect_string)
            else:
                response = self.native.send_command_expect(command)
        else:
            response = self.native.send_command_timing(command)

        if "Incorrect usage" in response or "Error:" in response:
            raise CommandError(command, response)

        return response

    def _uptime_components(self):
        """
        Retrieve days, hours, and minutes device has been up.

        Returns:
            tuple: The days, hours, and minutes device has been up as integers.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> days, hours, minutes = device._uptime_components
            >>> print(days)
            83
            >>>
        """
        sysinfo = self.show("show sysinfo")
        re_uptime = r"^System\s+Up\s+Time\.+\s*(.+?)\s*$"
        uptime = re.search(re_uptime, sysinfo, re.M)
        uptime_string = uptime.group()

        match_days = re.search(r"(\d+) days?", uptime_string)
        match_hours = re.search(r"(\d+) hrs?", uptime_string)
        match_minutes = re.search(r"(\d+) mins?", uptime_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0

        return days, hours, minutes

    def _wait_for_device_reboot(self, timeout=3600):
        """
        Wait for the device to finish reboot process and become accessible.

        Args:
            timeout (int): The length of time before considering the device unreachable.

        Raises:
            RebootTimeoutError: When a connection to the device is not established within the ``timeout`` period.

        Example:
            >>> device = AIREOSDevice(**connection_args):
            >>> device.reboot()
            >>> device._wait_for_device_reboot()
            >>> device.connected()
            True
            >>>
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                return
            except:  # noqa E722
                pass

        # TODO: Get proper hostname parameter
        raise RebootTimeoutError(hostname=self.host, wait_time=timeout)

    def backup_running_config(self, filename):
        raise NotImplementedError

    @property
    def boot_options(self):
        """
        The images that are candidates for booting on reload.

        Returns:
            dict: The boot options on the device. The "sys" key is the expected image on reload.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.boot_options
            {
                'backup': '8.8.125.0',
                'primary': '8.9.110.0',
                'sys': '8.9.110.0'
            }
            >>>
        """
        show_boot_out = self.show("show boot")
        re_primary_path = r"^Primary\s+Boot\s+Image\s*\.+\s*(?P<primary>\S+)(?P<status>.*)$"
        re_backup_path = r"^Backup\s+Boot\s+Image\s*\.+\s*(?P<backup>\S+)(?P<status>.*)$"
        primary = re.search(re_primary_path, show_boot_out, re.M)
        backup = re.search(re_backup_path, show_boot_out, re.M)
        if primary:
            result = primary.groupdict()
            primary_status = result.pop("status")
            result.update(backup.groupdict())
            backup_status = result.pop("status")
            if "default" in primary_status:
                result["sys"] = result["primary"]
            elif "default" in backup_status:
                result["sys"] = result["backup"]
            else:
                result["sys"] = None
        else:
            result = {"sys": None}
        return result

    def checkpoint(self, filename):
        raise NotImplementedError

    def close(self):
        """Close the SSH connection to the device."""
        if self._connected:
            self.native.disconnect()
            self._connected = False

    def config(self, command):
        """
        Configure the device with a single command.

        Args:
            command (str): The configuration command to send to the device.
                           The command should not include the "config" keyword.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.config("boot primary")
            >>>

        Raises:
            CommandError: When the device's response indicates the command failed.
        """
        self._enter_config()
        self._send_command(command)
        self.native.exit_config_mode()

    def config_list(self, commands):
        """
        Send multiple configuration commands to the device.

        Args:
            commands (list): The list of commands to send to the device.
                             The commands should not include the "config" keyword.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.config_list(["interface hostname virtual wlc1.site.com", "config interface vlan airway 20"])
            >>>

        Raises:
            COmmandListError: When the device's response indicates an error from sending one of the commands.
        """
        self._enter_config()
        entered_commands = []
        for command in commands:
            entered_commands.append(command)
            try:
                self._send_command(command)
            except CommandError as e:
                self.native.exit_config_mode()
                raise CommandListError(entered_commands, command, e.cli_error_msg)
        self.native.exit_config_mode()

    @property
    def connected(self):
        """
        The connection status of the device.

        Returns:
            bool: True if the device is connected, else False.
        """
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value

    def enable(self):
        """
        Ensure device is in enable mode.

        Returns:
            None: Device prompt is set to enable mode.
        """
        # Netmiko reports enable and config mode as being enabled
        if not self.native.check_enable_mode():
            self.native.enable()
        # Ensure device is not in config mode
        if self.native.check_config_mode():
            self.native.exit_config_mode()

    @property
    def facts(self):
        raise NotImplementedError

    def file_copy(self, username, password, server, filepath, protocol="sftp", filetype="code", delay_factor=3):
        """
        Copy a file from server to Controller.

        Args:
            username (str): The username to authenticate with the ``server``.
            password (str): The password to authenticate with the ``server``.
            server (str): The address of the file server.
            filepath (str): The full path to the file on the ``server``.
            protocol (str): The transfer protocol to use to transfer the file.
            filetype (str): The type of file per aireos definitions.
            delay_factor (int): The Netmiko delay factor to wait for device to complete transfer.

        Returns:
            bool: True when the file was transferred, False when the file is deemed to already be on the device.

        Raises:
            FileTransferError: When an error is detected in transferring the file.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.boot_options
            {
                'backup': '8.8.125.0',
                'primary': '8.9.100.0',
                'sys': '8.9.100.0'
            }
            >>> device.file_copy("user", "password", "10.1.1.1", "/images/aireos/AIR-CT5500-K9-8-10-105-0.aes")
            >>> device.boot_options
            {
                'backup': '8.9.100.0',
                'primary': '8.10.105.0',
                'sys': '8.10.105.0'
            }
            >>>
        """
        self.enable()
        filedir, filename = os.path.split(filepath)
        if filetype == "code":
            version = convert_filename_to_version(filename)
            if version in self.boot_options.values():
                return False
        try:
            self.show_list(
                [
                    f"transfer download datatype {filetype}",
                    f"transfer download mode {protocol}",
                    f"transfer download username {username}",
                    f"transfer download password {password}",
                    f"transfer download serverip {server}",
                    f"transfer download path {filedir}/",
                    f"transfer download filename {filename}",
                ]
            )
            response = self.native.send_command_timing("transfer download start")
            if "Are you sure you want to start? (y/N)" in response:
                response = self.native.send_command(
                    "y", expect_string="File transfer is successful.", delay_factor=delay_factor
                )

        except:  # noqa E722
            raise FileTransferError

        return True

    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        raise NotImplementedError

    def install_os(self, image_name, controller="both", save_config=True, **vendor_specifics):
        """
        Install an operating system on the controller.

        Args:
            image_name (str): The version to install on the device.
            controller (str): The controller(s) to reboot for install (only applies to HA device).
            save_config (bool): Whether the config should be saved to the device before reboot.

        Returns:
            bool: True when the install is successful, False when the version is deemed to already be running.

        Raises:
            OSInstallError: When the device is not booted with the specified image after reload.
            RebootTimeoutError: When the device is unreachable longer than the reboot timeout value.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.boot_options
            {
                'backup': '8.8.125.0',
                'primary': '8.9.100.0',
                'sys': '8.9.100.0'
            }
            >>> device.file_copy("user", "password", "10.1.1.1", "/images/aireos/AIR-CT5500-K9-8-10-105-0.aes")
            >>> device.boot_options
            {
                'backup': '8.9.100.0',
                'primary': '8.10.105.0',
                'sys': '8.10.105.0'
            }
            >>> device.install_os("8.10.105.0")
            >>>
        """
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            self.set_boot_options(image_name, **vendor_specifics)
            self.reboot(confirm=True, controller=controller, save_config=save_config)
            self._wait_for_device_reboot(timeout=timeout)
            if not self._image_booted(image_name):
                raise OSInstallError(hostname=self.host, desired_boot=image_name)

            return True

        return False

    def open(self):
        """
        Open a connection to the controller.

        This method will close the connection if it is determined that it is the standby controller.
        """
        if self.connected:
            try:
                self.native.find_prompt()
            except:  # noqa E722
                self.connected = False

        if not self.connected:
            self.native = ConnectHandler(
                device_type="cisco_wlc",
                ip=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                global_delay_factor=self.global_delay_factor,
                secret=self.secret,
                verbose=False,
            )
            self.connected = True

        # This prevents open sessions from connecting to STANDBY WLC
        if not self.redundancy_state:
            self.close()

    def reboot(self, timer=0, confirm=False, controller="self", save_config=True):
        """
        Reload the controller or controller pair.

        Args:
            timer (int): The time to wait before reloading.
            confirm (bool): Whether to reboot the device or not.
            controller (str): Which controller(s) to reboot (only applies to HA pairs).
            save_config (bool): Whether the configuraion should be saved before reload.

        Raises:
            ReloadTimeoutError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.reboot(confirm=True)
            >>>
        """
        if confirm:

            def handler(signum, frame):
                raise RebootSignal("Interrupting after reload")

            signal.signal(signal.SIGALRM, handler)

            if self.redundancy_mode != "sso disabled":
                reboot_command = f"reset system {controller}"
            else:
                reboot_command = "reset system"

            if timer:
                reboot_command += f" in {timer}"

            if save_config:
                self.save()

            signal.alarm(20)
            try:
                response = self.native.send_command_timing(reboot_command)
                if "save" in response:
                    if not save_config:
                        response = self.native.send_command_timing("n")
                    else:
                        response = self.native.send_command_timing("y")
                if "reset" in response:
                    self.native.send_command_timing("y")
            except RebootSignal:
                signal.alarm(0)

            signal.alarm(0)
        else:
            print("Need to confirm reboot with confirm=True")

    @property
    def redundancy_mode(self):
        """
        The oprating redundancy mode of the controller.

        Returns:
            str: The redundancy mode the device is operating in.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.redundancy_mode
            'sso enabled'
            >>>
        """
        ha = self.show("show redundancy summary")
        ha_mode = re.search(r"^\s*Redundancy\s+Mode\s*=\s*(.+?)\s*$", ha, re.M)
        return ha_mode.group(1).lower()

    @property
    def redundancy_state(self):
        """
        Determine if device is currently the active device.

        Returns:
            bool: True if the device is active, False if the device is standby.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.redundancy_state
            True
            >>>
        """
        ha = self.show("show redundancy summary")
        ha_state = re.search(r"^\s*Local\s+State\s*=\s*(.+?)\s*$", ha, re.M)
        if ha_state.group(1).lower() == "active":
            return True
        else:
            return False

    def rollback(self):
        raise NotImplementedError

    @property
    def running_config(self):
        raise NotImplementedError

    def save(self):
        """
        Save the configuration on the device.

        Returns:
            bool: True if the save command did not fail.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.save()
            >>>
        """
        self.native.save_config()
        return True

    def set_boot_options(self, image_name, **vendor_specifics):
        """
        Set the version to boot on the device.

        Args:
            image_name (str): The version to boot into on next reload.

        Raises:
            NTCFileNotFoundError: When the version is not listed in ``boot_options``.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.boot_options
            {
                'backup': '8.8.125.0',
                'primary': '8.9.100.0',
                'sys': '8.9.100.0'
            }
            >>> device.set_boot_options("8.8.125.0")
            >>> device.boot_options
            {
                'backup': '8.8.125.0',
                'primary': '8.9.100.0',
                'sys': '8.8.125.0'
            }
        """
        if self.boot_options["primary"] == image_name:
            boot_command = "boot primary"
        elif self.boot_options["backup"] == image_name:
            boot_command = "boot backup"
        else:
            raise NTCFileNotFoundError(image_name, "'show boot'", self.host)
        self.config(boot_command)
        self.save()
        if not self.boot_options["sys"] == image_name:
            raise CommandError(
                command=boot_command, message="Setting boot command did not yield expected results",
            )

    def show(self, command, expect=False, expect_string=""):
        """
        Send an operational command to the device.

        Args:
            command (str): The command to send to the device.
            expect (bool): Whether to send a different expect string than normal prompt.
            expect_string (str): The expected prompt after running the command.

        Returns:
            str: The data returned from the device

        Raises:
            CommandError: When the returned data indicates the command failed.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> sysinfo = device._send_command("show sysinfo")
            >>> print(sysinfo)
            Product Version.....8.2.170.0
            System Up Time......3 days 2 hrs 20 mins 30 sec
            ...
            >>>
        """
        self.enable()
        return self._send_command(command, expect=expect, expect_string=expect_string)

    def show_list(self, commands):
        """
        Send an operational command to the device.

        Args:
            commands (list): The list of commands to send to the device.
            expect (bool): Whether to send a different expect string than normal prompt.
            expect_string (str): The expected prompt after running the command.

        Returns:
            list: The data returned from the device for all commands.

        Raises:
            CommandListError: When the returned data indicates one of the commands failed.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> command_data = device._send_command(["show sysinfo", "show boot"])
            >>> print(command_data[0])
            Product Version.....8.2.170.0
            System Up Time......3 days 2 hrs 20 mins 30 sec
            ...
            >>> print(command_data[1])
            Primary Boot Image............................... 8.2.170.0 (default) (active)
            Backup Boot Image................................ 8.5.110.0
            >>>
        """
        self.enable()

        responses = []
        entered_commands = []
        for command in commands:
            entered_commands.append(command)
            try:
                responses.append(self._send_command(command))
            except CommandError as e:
                raise CommandListError(entered_commands, command, e.cli_error_msg)

        return responses

    @property
    def startup_config(self):
        raise NotImplementedError

    @property
    def uptime(self):
        """
        The uptime of the device in seconds.

        Returns:
            int: The number of seconds the device has been up.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.uptime
            109303
            >>>
        """
        days, hours, minutes = self._uptime_components()
        hours += days * 24
        minutes += hours * 60
        seconds = minutes * 60
        return seconds

    @property
    def uptime_string(self):
        """
        The uptime of the device as a string.
        The format is dd::hh::mm

        Returns:
            str: The uptime of the device.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.uptime_string
            22:04:39
            >>>
        """
        days, hours, minutes = self._uptime_components()
        return "%02d:%02d:%02d:00" % (days, hours, minutes)


class RebootSignal(NTCError):
    """Handles reboot interrupts."""

    pass
