"""Module for using a Cisco IOS device over SSH.
"""

import signal
import os
import re
import time
import warnings

from netmiko import ConnectHandler
from netmiko import FileTransfer

from pyntc.utils import get_structured_data
from .base_device import BaseDevice, RollbackError, fix_docs
from pyntc.errors import (
    NTCError,
    CommandError,
    OSInstallError,
    CommandListError,
    FileTransferError,
    RebootTimeoutError,
    DeviceNotActiveError,
    NTCFileNotFoundError,
    FileSystemNotFoundError,
    SocketClosedError,
)


BASIC_FACTS_KM = {"model": "hardware", "os_version": "version", "serial_number": "serial", "hostname": "hostname"}
RE_SHOW_REDUNDANCY = re.compile(
    r"^Redundant\s+System\s+Information\s*:\s*\n^-.+-\s*\n(?P<info>.+?)\n"
    r"^Current\s+Processor\s+Information\s*:\s*\n^-.+-\s*\n(?P<self>.+?$)\n"
    r"(?:Peer\s+Processor\s+Information\s*:\s*\n-.+-\s*\n(?P<other>.+)|Peer\s+\(slot:\s+\d+\).+)",
    re.DOTALL | re.MULTILINE,
)
RE_REDUNDANCY_OPERATION_MODE = re.compile(r"^\s*Operating\s+Redundancy\s+Mode\s*=\s*(.+?)\s*$", re.M)
RE_REDUNDANCY_STATE = re.compile(r"^\s*Current\s+Software\s+state\s*=\s*(.+?)\s*$", re.M)
SHOW_DIR_RETRY_COUNT = 5
INSTALL_MODE_FILE_NAME = "packages.conf"


@fix_docs
class IOSDevice(BaseDevice):
    """Cisco IOS Device Implementation."""

    vendor = "cisco"
    active_redundancy_states = {None, "active"}

    def __init__(self, host, username, password, secret="", port=22, confirm_active=True, fast_cli=True, **kwargs):
        """
        PyNTC Device implementation for Cisco IOS.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            secret (str): The password to escalate privilege on the device.
            port (int): The port to use to establish the connection.
            confirm_active (bool): Determines if device's high availability state should be validated before leaving connection open.
            fast_cli (bool): Fast CLI mode for Netmiko, it is recommended to use False when opening the client on code upgrades
        """
        super().__init__(host, username, password, device_type="cisco_ios_ssh")

        self.native = None
        self.secret = secret
        self.port = int(port)
        self.global_delay_factor = kwargs.get("global_delay_factor", 1)
        self.delay_factor = kwargs.get("delay_factor", 1)
        self._fast_cli = fast_cli
        self._connected = False
        self.open(confirm_active=confirm_active)

    def _check_command_output_for_errors(self, command, command_response):
        """
        Check response from device to see if an error was reported.

        Args:
            command (str): The command that was sent to the device.

        Raises:
            CommandError: When ``command_response`` reports an error in sending ``command``.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> command = "show version"
            >>> command_response = "output from show version"
            >>> device._check_command_output_for_errors(command, command_response)
            >>> command = "invalid command"
            >>> command_response = "% invalid command"
            >>> device._check_command_output_for_errors(command, command_resposne)
            CommandError: ...
            >>>
        """
        if "% " in command_response or "Error:" in command_response:
            raise CommandError(command, command_response)

    def _enable(self):
        warnings.warn("_enable() is deprecated; use enable().", DeprecationWarning)
        self.enable()

    def _enter_config(self):
        self.enable()
        self.native.config_mode()

    def _file_copy_instance(self, src, dest=None, file_system="flash:"):
        if dest is None:
            dest = os.path.basename(src)

        fc = FileTransfer(self.native, src, dest, file_system=file_system)
        return fc

    def _get_file_system(self):
        """Determines the default file system or directory for device.

        Returns:
            str: The name of the default file system or directory for the device.

        Raises:
            FileSystemNotFound: When the module is unable to determine the default file system.
        """
        # Set variables to control while loop
        counter = 0

        # Attempt to gather file system
        while counter < SHOW_DIR_RETRY_COUNT:
            counter += 1
            raw_data = self.show("dir")
            try:
                file_system = re.match(r"\s*.*?(\S+:)", raw_data).group(1)
                return file_system
            except AttributeError:
                # Allow to continue through the loop
                continue

        raise FileSystemNotFoundError(hostname=self.hostname, command="dir")

    # Get the version of the image that is booted into on the device
    def _image_booted(self, image_name, image_pattern=r".*\.(\d+\.\d+\.\w+)\.SPA.+", **vendor_specifics):
        version_data = self.show("show version")
        if re.search(image_name, version_data):
            return True

        # Test for version number in the text, used on install mode devices that use packages.conf
        try:
            version_number = re.search(image_pattern, image_name).group(1)
            if version_number and version_number in version_data:
                return True
        # Continue on if regex is unable to find the result, which raises an attribute error
        except AttributeError:
            pass

        # Unable to find the version number in output, the image is not booted.
        return False

    def _interfaces_detailed_list(self):
        ip_int_br_out = self.show("show ip int br")
        ip_int_br_data = get_structured_data("cisco_ios_show_ip_int_brief.template", ip_int_br_out)

        return ip_int_br_data

    def _is_catalyst(self):
        return self.model.startswith("WS-")

    def _raw_version_data(self):
        show_version_out = self.show("show version")
        try:
            version_data = get_structured_data("cisco_ios_show_version.template", show_version_out)[0]
        except IndexError:
            return {}

        return version_data

    def _send_command(self, command, expect_string=None, **kwargs):
        # Set command args and assign the command to command_string argument
        command_args = {"command_string": command}

        # Check for an expect_string being passed in
        if expect_string is not None:
            command_args["expect_string"] = expect_string

        # Update command_args with additional arguments passed in, must be a valid Netmiko argument
        command_args.update(kwargs)

        response = self.native.send_command(**command_args)

        if "% " in response or "Error:" in response:
            raise CommandError(command, response)

        return response

    def _show_vlan(self):
        show_vlan_out = self.show("show vlan")
        show_vlan_data = get_structured_data("cisco_ios_show_vlan.template", show_vlan_out)

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
                self.show("show version")
                return
            except:  # noqa E722 # nosec
                pass

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        with open(filename, "w") as f:
            f.write(self.running_config)

    @property
    def boot_options(self):
        boot_path_regex = r"(?:BOOT variable\s+=\s+(\S+)\s*$|BOOT path-list\s+:\s*(\S+)\s*$)"
        try:
            # Try show bootvar command first
            show_boot_out = self.show("show bootvar")
            show_boot_out = show_boot_out.split("Boot Variables on next reload", 1)[-1]
        except CommandError:
            try:
                # Try show boot if previous command was invalid
                show_boot_out = self.show("show boot")
                show_boot_out = show_boot_out.split("Boot Variables on next reload", 1)[-1]
            except CommandError:
                # Default to running config value
                show_boot_out = self.show("show run | inc boot")
                boot_path_regex = r"boot\s+system\s+(?:\S+\s+|)(\S+)\s*$"

        match = re.search(boot_path_regex, show_boot_out, re.MULTILINE)
        if match:
            boot_path_tuple = match.groups()
            # The regex match will return two values: the boot value and None
            # The return order will depend on which side of the `or` is matched in the regex
            boot_path = [value for value in boot_path_tuple if value is not None][0]
            file_system = self._get_file_system()
            boot_image = boot_path.replace(file_system, "")
            boot_image = boot_image.replace("/", "")
            boot_image = boot_image.split(",")[0]
            boot_image = boot_image.split(";")[0]
        else:
            boot_image = None

        return {"sys": boot_image}

    def checkpoint(self, checkpoint_file):
        self.save(filename=checkpoint_file)

    def close(self):
        if self.connected:
            self.native.disconnect()
            self._connected = False

    def config(self, command, **netmiko_args):
        """
        Send config commands to device.

        By default, entering and exiting config mode is handled automatically.
        To disable entering and exiting config mode, pass `enter_config_mode` and `exit_config_mode` in ``**netmiko_args``.
        This supports all arguments supported by Netmiko's `send_config_set` method using ``netmiko_args``.
        This will send each command in ``command`` until either an Error is caught or all commands have been sent.

        Args:
            command (str|list): The command or commands to send to the device.
            **netmiko_args: Any argument supported by ``netmiko.ConnectHandler.send_config_set``.

        Returns:
            str: When ``command`` is a str, the config session input and output from sending ``command``.
            list: When ``command`` is a list, the config session input and output from sending ``command``.

        Raises:
            TypeError: When sending an argument in ``**netmiko_args`` that is not supported.
            CommandError: When ``command`` is a str and its results report an error.
            CommandListError: When ``command`` is a list and one of the commands reports an error.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.config("no service pad")
            'configure terminal\nEnter configuration commands, one per line.  End with CNTL/Z.\n'
            'host(config)#no service pad\nhost(config)#end\nhost#'
            >>> device.config(["interface Gig0/1", "description x-connect"])
            ['host(config)#interface Gig0/1\nhost(config-if)#, 'description x-connect\nhost(config-if)#']
            >>>
        """
        # TODO: Remove this when deprecating config_list method
        original_command_is_str = isinstance(command, str)

        if original_command_is_str:  # TODO: switch to isinstance(command, str) when removing above
            command = [command]

        original_exit_config_setting = netmiko_args.get("exit_config_mode")
        netmiko_args["exit_config_mode"] = False
        # Ignore None or invalid args passed for enter_config_mode
        if netmiko_args.get("enter_config_mode") is not False:
            self._enter_config()
            netmiko_args["enter_config_mode"] = False

        entered_commands = []
        command_responses = []
        try:
            for cmd in command:
                entered_commands.append(cmd)
                command_response = self.native.send_config_set(cmd, **netmiko_args)
                command_responses.append(command_response)
                self._check_command_output_for_errors(cmd, command_response)
        except TypeError as err:
            raise TypeError(f"Netmiko Driver's {err.args[0]}")
        # TODO: Remove this when deprecating config_list method
        except CommandError as err:
            if not original_command_is_str:
                raise CommandListError(entered_commands, cmd, err.cli_error_msg)
            else:
                raise err
        # Don't let exception prevent exiting config mode
        finally:
            # Ignore None or invalid args passed for exit_config_mode
            if original_exit_config_setting is not False:
                self.native.exit_config_mode()

        # TODO: Remove this when deprecating config_list method
        if original_command_is_str:
            return command_responses[0]

        return command_responses

    def config_list(self, commands, **netmiko_args):
        """
        DEPRECATED - Use the `config` method.

        Send config commands to device.

        By default, entering and exiting config mode is handled automatically.
        To disable entering and exiting config mode, pass `enter_config_mode` and `exit_config_mode` in ``**netmiko_args``.
        This supports all arguments supported by Netmiko's `send_config_set` method using ``netmiko_args``.

        Args:
            commands (list): The commands to send to the device.
            **netmiko_args: Any argument supported by ``netmiko.ConnectHandler.send_config_set``.

        Returns:
            list: Each command's input and output from sending the command in ``commands``.

        Raises:
            TypeError: When sending an argument in ``**netmiko_args`` that is not supported.
            CommandListError: When one of the commands reports an error on the device.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.config_list(["interface Gig0/1", "description x-connect"])
            ['host(config)#interface Gig0/1\nhost(config-if)#, 'description x-connect\nhost(config-if)#']
            >>>
        """
        warnings.warn("config_list() is deprecated; use config.", DeprecationWarning)
        return self.config(commands, **netmiko_args)

    def confirm_is_active(self):
        """
        Confirm that the device is either standalone or the active device in a high availability cluster.

        Returns:
            bool: True when the device is considered active.

        Rasies:
            DeviceNotActiveError: When the device is not considered the active device.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.redundancy_state
            'standby hot'
            >>> device.confirm_is_active()
            raised DeviceNotActiveError:
            host1 is not the active device.

            device state: standby hot
            peer state:   active

            >>> device.redundancy_state
            'active'
            >>> device.confirm_is_active()
            True
            >>>
        """
        if not self.is_active():
            redundancy_state = self.redundancy_state
            peer_redundancy_state = self.peer_redundancy_state
            self.close()
            raise DeviceNotActiveError(self.host, redundancy_state, peer_redundancy_state)

        return True

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

    @property
    def uptime(self):
        if self._uptime is None:
            version_data = self._raw_version_data()
            uptime_full_string = version_data["uptime"]
            self._uptime = self._uptime_to_seconds(uptime_full_string)

        return self._uptime

    @property
    def uptime_string(self):
        if self._uptime_string is None:
            version_data = self._raw_version_data()
            uptime_full_string = version_data["uptime"]
            self._uptime_string = self._uptime_to_string(uptime_full_string)

        return self._uptime_string

    @property
    def hostname(self):
        version_data = self._raw_version_data()
        if self._hostname is None:
            self._hostname = version_data["hostname"]

        return self._hostname

    @property
    def interfaces(self):
        if self._interfaces is None:
            self._interfaces = list(x["intf"] for x in self._interfaces_detailed_list())

        return self._interfaces

    @property
    def vlans(self):
        if self._vlans is None:
            if self.model.startswith("WS"):
                self._vlans = list(str(x["vlan_id"]) for x in self._show_vlan())
            else:
                self._vlans = []

        return self._vlans

    @property
    def fqdn(self):
        if self._fqdn is None:
            self._fqdn = "N/A"

        return self._fqdn

    @property
    def model(self):
        version_data = self._raw_version_data()
        if self._model is None:
            self._model = version_data["hardware"]

        return self._model

    @property
    def os_version(self):
        version_data = self._raw_version_data()
        if self._os_version is None:
            self._os_version = version_data["version"]

        return self._os_version

    @property
    def serial_number(self):
        version_data = self._raw_version_data()
        if self._serial_number is None:
            self._serial_number = version_data["serial"]

        return self._serial_number

    @property
    def config_register(self):
        # ios-specific facts
        version_data = self._raw_version_data()
        self._config_register = version_data["config_register"]

        return self._config_register

    @property
    def fast_cli(self):
        return self._fast_cli

    @fast_cli.setter
    def fast_cli(self, value):
        self._fast_cli = value
        self.native.fast_cli = value

    def file_copy(self, src, dest=None, file_system=None):
        self.enable()
        if file_system is None:
            file_system = self._get_file_system()

        if not self.file_copy_remote_exists(src, dest, file_system):
            fc = self._file_copy_instance(src, dest, file_system=file_system)
            #        if not self.fc.verify_space_available():
            #            raise FileTransferError('Not enough space available.')

            try:
                fc.enable_scp()
                fc.establish_scp_conn()
                fc.transfer_file()
            except OSError as error:
                # compare hashes
                if not fc.compare_md5():
                    raise SocketClosedError(message=error)
            except:  # noqa E722
                raise FileTransferError
            finally:
                fc.close_scp_chan()

            # Ensure connection to device is still open after long transfers
            self.open()

            if not self.file_copy_remote_exists(src, dest, file_system):
                raise FileTransferError(
                    message="Attempted file copy, but could not validate file existed after transfer"
                )

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, file_system=None):
        self.enable()
        if file_system is None:
            file_system = self._get_file_system()

        fc = self._file_copy_instance(src, dest, file_system=file_system)
        if fc.check_file_exists() and fc.compare_md5():
            return True
        return False

    def install_os(self, image_name, install_mode=False, install_mode_delay_factor=20, **vendor_specifics):
        """Installs the prescribed Network OS, which must be present before issuing this command.

        Args:
            image_name (str): Name of the IOS image to boot into
            install_mode (bool, optional): Uses newer install method on devices. Defaults to False.

        Raises:
            OSInstallError: Unable to install OS Error type

        Returns:
            bool: False if no install is needed, true if the install completes successfully
        """
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            if install_mode:
                # Change boot statement to be boot system <flash>:packages.conf
                self.set_boot_options(INSTALL_MODE_FILE_NAME, **vendor_specifics)

                # Get the current fast_cli to set it back later to whatever it is
                current_fast_cli = self.fast_cli

                # Set fast_cli to False to handle install mode, 10+ minute installation
                self.fast_cli = False

                # Check for OS Version specific upgrade path
                # https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9300/software/release/17-2/release_notes/ol-17-2-9300.html
                os_version = self.os_version
                if "16.5.1a" in os_version or "16.6.1" in os_version:
                    # Run install command and reboot device
                    command = f"request platform software package install switch all file {self._get_file_system()}{image_name} auto-copy"
                    self.show(command, delay_factor=install_mode_delay_factor)
                    self.reboot()

                else:
                    # Run install command (which reboots the device)
                    command = (
                        f"install add file {self._get_file_system()}{image_name} activate commit prompt-level none"
                    )
                    # Set a higher delay factor and send it in
                    try:
                        self.show(command, delay_factor=install_mode_delay_factor)
                    except IOError:
                        pass

            else:
                self.set_boot_options(image_name, **vendor_specifics)
                self.reboot()

            # Wait for the reboot to finish
            self._wait_for_device_reboot(timeout=timeout)

            # Set FastCLI back to originally set when using install mode
            if install_mode:
                self.fast_cli = current_fast_cli

            # Verify the OS level
            if not self._image_booted(image_name):
                raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

            return True

        return False

    def is_active(self):
        """
        Determine if the current processor is the active processor.

        Returns:
            bool: True if the processor is active or does not support HA, else False.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.is_active()
            True
            >>>
        """
        return self.redundancy_state in self.active_redundancy_states

    def open(self, confirm_active=True):
        """
        Open a connection to the network device.

        This method will close the connection if ``confirm_active`` is True and the device is not active.
        Devices that do not have high availability are considered active.

        Args:
            confirm_active (bool): Determines if device's high availability state should be validated before leaving connection open.

        Raises:
            DeviceNotActiveError: When ``confirm_active`` is True, and the device high availability state is not active.

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
            except:  # noqa E722
                self._connected = False

        if not self.connected:
            self.native = ConnectHandler(
                device_type="cisco_ios",
                ip=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                global_delay_factor=self.global_delay_factor,
                secret=self.secret,
                verbose=False,
                fast_cli=self.fast_cli,
            )
            self._connected = True

        if confirm_active:
            self.confirm_is_active()

    @property
    def peer_redundancy_state(self):
        """
        Determine the current redundancy state of the peer processor.

        Returns:
            str: The redundancy state of the peer processor.
            None: When the processor does not support redundancy.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.peer_redundancy_state
            'standby hot'
            >>>
        """
        try:
            show_redundancy = self.show("show redundancy")
        except CommandError:
            return None
        re_show_redundancy = RE_SHOW_REDUNDANCY.match(show_redundancy.lstrip())
        processor_redundancy_info = re_show_redundancy.group("other")
        if processor_redundancy_info is not None:
            re_redundancy_state = RE_REDUNDANCY_STATE.search(processor_redundancy_info)
            processor_redundancy_state = re_redundancy_state.group(1).lower()
        else:
            processor_redundancy_state = "disabled"
        return processor_redundancy_state

    def reboot(self, timer=0, **kwargs):
        """Reboot device.
        Reload the controller or controller pair.

        Args:
            timer (int): The time to wait before reloading.

        Raises:
            ReloadTimeoutError: When the device is still unreachable after the timeout period.
        """
        if kwargs.get("confirm"):
            warnings.warn("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        def handler(signum, frame):
            raise RebootSignal("Interrupting after reload")

        signal.signal(signal.SIGALRM, handler)
        signal.alarm(10)

        try:
            if timer > 0:
                first_response = self.native.send_command_timing("reload in %d" % timer)
            else:
                first_response = self.native.send_command_timing("reload")

            if "System configuration" in first_response:
                self.native.send_command_timing("no")

            self.native.send_command_timing("\n")
        except RebootSignal:
            signal.alarm(0)

        signal.alarm(0)
        # else:
        #     print("Need to confirm reboot with confirm=True")

    @property
    def redundancy_mode(self):
        """
        The operating redundancy mode of the device.

        Returns:
            str: The redundancy mode the device is operating in.
                If the command is not supported, then "n/a" is returned.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.redundancy_mode
            'stateful switchover'
            >>>
        """
        try:
            show_redundancy = self.show("show redundancy")
        except CommandError:
            return "n/a"
        re_show_redundancy = RE_SHOW_REDUNDANCY.match(show_redundancy.lstrip())
        redundancy_info = re_show_redundancy.group("info")
        re_redundancy_mode = RE_REDUNDANCY_OPERATION_MODE.search(redundancy_info)
        redundancy_mode = re_redundancy_mode.group(1).lower()
        return redundancy_mode

    @property
    def redundancy_state(self):
        """
        Determine the current redundancy state of the processor.

        Returns:
            str: The redundancy state of the current processor.
            None: When the processor does not support redundancy.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.redundancy_state
            'active'
            >>>
        """
        try:
            show_redundancy = self.show("show redundancy")
        except CommandError:
            return None
        re_show_redundancy = RE_SHOW_REDUNDANCY.match(show_redundancy.lstrip())
        processor_redundancy_info = re_show_redundancy.group("self")
        re_redundancy_state = RE_REDUNDANCY_STATE.search(processor_redundancy_info)
        processor_redundancy_state = re_redundancy_state.group(1).lower()
        return processor_redundancy_state

    def rollback(self, rollback_to):
        try:
            self.show("configure replace flash:%s force" % rollback_to)
        except CommandError:
            raise RollbackError("Rollback unsuccessful. %s may not exist." % rollback_to)

    @property
    def running_config(self):
        return self.show("show running-config")

    def save(self, filename="startup-config"):
        command = "copy running-config %s" % filename
        # Changed to send_command_timing to not require a direct prompt return.
        self.native.send_command_timing(command)
        # If the user has enabled 'file prompt quiet' which dose not require any confirmation or feedback.
        # This will send return without requiring an OK.
        # Send a return to pass the [OK]? message - Incease delay_factor for looking for response.
        self.native.send_command_timing("\n", delay_factor=2)
        # Confirm that we have a valid prompt again before returning.
        self.native.find_prompt()
        return True

    def set_boot_options(self, image_name, **vendor_specifics):
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = self._get_file_system()

        file_system_files = self.show("dir {0}".format(file_system))
        if re.search(image_name, file_system_files) is None:
            raise NTCFileNotFoundError(hostname=self.hostname, file=image_name, dir=file_system)

        try:
            command = "boot system {0}/{1}".format(file_system, image_name)
            self.config(["no boot system", command])
        except CommandListError:  # TODO: Update to CommandError when deprecating config_list
            file_system = file_system.replace(":", "")
            command = "boot system {0} {1}".format(file_system, image_name)
            self.config(["no boot system", command])

        self.save()
        new_boot_options = self.boot_options["sys"]
        if new_boot_options != image_name:
            raise CommandError(
                command=command,
                message="Setting boot command did not yield expected results, found {0}".format(new_boot_options),
            )

    def show(self, command, expect_string=None):
        self.enable()
        return self._send_command(command, expect_string=expect_string)

    def show_list(self, commands):
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
        return self.show("show startup-config")


class RebootSignal(NTCError):
    pass
