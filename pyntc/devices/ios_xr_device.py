"""Module for using a Cisco IOS device over SSH."""

import os
import re
import time

from netmiko import ConnectHandler, file_transfer
from netmiko.exceptions import ReadTimeout
from ntc_templates.parse import parse_output
from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs, RollbackError
from pyntc.errors import (
    CommandError,
    CommandListError,
    DeviceNotActiveError,
    FileTransferError,
    NTCError,
    RebootTimeoutError,
)
from pyntc.utils import get_structured_data


BASIC_FACTS_KM = {"model": "hardware", "os_version": "version", "serial_number": "serial", "hostname": "hostname"}
SHOW_DIR_RETRY_COUNT = 5
INSTALL_MODE_FILE_NAME = "packages.conf"


@fix_docs
class IOSXRDevice(BaseDevice):
    """Cisco IOSXR Device Implementation."""

    vendor = "cisco"
    active_redundancy_states = {None, "active"}

    def __init__(  # nosec
        self, host, username, password, secret="", port=None, confirm_active=True, **kwargs
    ):  # noqa: D403
        """
        PyNTC Device implementation for Cisco IOSXR.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            secret (str): The password to escalate privilege on the device.
            port (int): The port to use to establish the connection. Defaults to 22.
            confirm_active (bool): Determines if device's high availability state should be validated before leaving connection open.
        """
        super().__init__(host, username, password, device_type="cisco_iosxr_ssh")

        self.native = None
        self.secret = secret
        self.port = int(port) if port else 22
        self.read_timeout_override = kwargs.get("read_timeout_override")
        self._connected = False
        self.open(confirm_active=confirm_active)
        log.init(host=host)

    def _check_command_output_for_errors(self, command, command_response):
        """
        Check response from device to see if an error was reported.

        Args:
            command (str): The command that was sent to the device.

        Raises:
            CommandError: When ``command_response`` reports an error in sending ``command``.

        Example:
            >>> device = IOSXRDevice(**connection_args)
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
        log.warning("_enable() is deprecated; use enable().")
        self.enable()
        log.debug("Host %s: Device enabled", self.host)

    def _enter_config(self):
        self.enable()
        self.native.config_mode()
        log.debug("Host %s: Device entered config mode.", self.host)

    def _file_copy_instance(self, src, dest=None, file_system="disk0:"):
        if dest is None:
            dest = os.path.basename(src)

        file_copy = file_transfer(self.native, src, dest, file_system=file_system)
        log.debug("Host %s: File copy instance %s.", self.host, file_copy)
        return file_copy

    # Get the version of the image that is booted into on the device
    def _image_booted(self, image_name, image_pattern=r".*\.(\d+\.\d+\.\w+)\.SPA.+", **vendor_specifics):
        version_data = self.show("show version")
        if re.search(image_name, version_data):
            log.info("Host %s: Image %s booted successfully.", self.host, image_name)
            return True

        log.info("Host %s: Image %s not booted successfully.", self.host, image_name)
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
        ip_int_br_out = self.show("show interfaces description")
        ip_int_br_data = parse_output(platform="cisco_xr", command="show interfaces description", data=ip_int_br_out)
        log.debug("Host %s: interfaces detailed list %s.", self.host, ip_int_br_data)
        return ip_int_br_data

    def _raw_version_data(self):
        show_version_out = self.show("show version")
        try:
            version_data = parse_output(platform="cisco_xr", command="show version", data=show_version_out)[0]
        except IndexError:
            log.error("Host %s: index error.", self.host)
            return {}

        log.debug("Host %s: version data %s.", self.host, version_data)
        return version_data

    def _raw_inventory_data(self):
        inventory_out = self.show("admin show inventory")
        try:
            inventory_data = parse_output(platform="cisco_xr", command="admin show inventory", data=inventory_out)
        except IndexError:
            log.error("Host %s: index error.", self.host)
            return {}

        log.debug("Host %s: platform data %s.", self.host, inventory_data)
        return inventory_data

    def _redundancy_check(self):
        """Determine the current redundancy state of the chassis."""
        try:
            show_redundancy = self.show("show redundancy")
        except CommandError:
            log.error("Host %s: Command error for command 'show redundancy'.", self.host)
            return "n/a"
        # Regular Expression patterns
        node_pattern = r"Redundancy information for node (\S+):"
        active_pattern = r"ode (\S+) is in ACTIVE role"
        standby_pattern = r"ode (\S+) is in STANDBY role"
        no_valid_pattern = r"ode (\S+) has no valid partner"
        # Extracted redundancy information
        current_node = active_node = standby_node = None
        if node_match := re.search(node_pattern, show_redundancy):
            current_node = node_match.group(1)
        if active_match := re.search(active_pattern, show_redundancy):
            active_node = active_match.group(1)
        if standby_match := re.search(standby_pattern, show_redundancy):
            standby_node = standby_match.group(1)

        # Logic to determine the redundancy state
        if current_node is None:
            # Means that the command failed somehow or CLI has changed
            raise ValueError("No valid redundancy information found")
        if no_valid_match := re.search(no_valid_pattern, show_redundancy):
            # No valid match means no stanby thefore standalone
            log.debug(f"no_valid_pattern matched for Node:{no_valid_match}")
            self._redundancy_mode = "STANDALONE"
        elif standby_node is not None:
            # Presence of a standby node means redundancy
            self._redundancy_mode = "REDUNDANT"
        else:
            # Means that there is a bug - A valid match and no standby
            raise ValueError("No valid redundancy information found")

        if active_node == current_node:
            self._redundancy_state = "active"

        elif standby_node == current_node:
            self._redundancy_state = "standby"
        else:
            # Means that there is a bug - A valid match and no standby
            raise ValueError("No valid redundancy information found")

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
            log.error("Host %s: Error in %s with response: %s", self.host, command, response)
            raise CommandError(command, response)

        log.info("Host %s: Command %s was executed successfully with response: %s", self.host, command, response)
        return response

    def _show_vlan(self):
        show_vlan_out = self.show("show vlan")
        show_vlan_data = get_structured_data("cisco_ios_show_vlan.template", show_vlan_out)

        log.debug("Host %s: Successfully executed command 'show vlan' with responses %s.", self.host, show_vlan_data)
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
        return f"{days:02d}:{hours:02d}:{minutes:02d}:00"

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                self.show("show version")
                log.debug("Host %s: Device reboot Completed.", self.host)
                if self._has_reload_happened_recently():
                    return
            except:  # noqa E722 # nosec  # pylint: disable=bare-except
                pass

        log.error("Host %s: Device timed out while rebooting.", self.host)
        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def _has_reload_happened_recently(self):
        if re.search(r"^00:00:0\d:*", self.uptime_string) is None:
            self._uptime_string = None
            return False
        return True

    @property
    def boot_options(self):
        """Get current boot image.

        Returns:
            dict: Key ``sys`` with value being the current boot image.
        """
        raise NotImplementedError

    def checkpoint(self, checkpoint_file):
        """Create checkpoint file.

        Args:
            checkpoint_file (str): Name of checkpoint file.
        """
        log.debug("Host %s: checkpoint is %s.", self.host, checkpoint_file)
        self.backup_to_disk(path=f"disk0:/{checkpoint_file}")

    def close(self):
        """Disconnect from device."""
        if self.connected:
            self.native.disconnect()
            self._connected = False
            log.debug("Host %s: Connection closed.", self.host)

    def config(self, command, **netmiko_args):
        r"""
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

        # TODO: switch to isinstance(command, str) when removing above
        if original_command_is_str:
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
            log.error("Host %s: Netmiko Driver's %s", self.host, err.args[0])
            raise TypeError(f"Netmiko Driver's {err.args[0]}")
        # TODO: Remove this when deprecating config_list method
        except CommandError as err:
            if not original_command_is_str:
                log.error(
                    "Host %s: Command error with commands: %s and error message %s",
                    self.host,
                    entered_commands,
                    err.cli_error_msg,
                )
                raise CommandListError(entered_commands, cmd, err.cli_error_msg)
            raise err
        # Don't let exception prevent exiting config mode
        finally:
            # Ignore None or invalid args passed for exit_config_mode
            if original_exit_config_setting is not False:
                self.native.exit_config_mode()

        # TODO: Remove this when deprecating config_list method
        if original_command_is_str:
            return command_responses[0]

        log.info("Host %s: Device configured with command responses %s.", self.host, command_responses)
        return command_responses

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
            log.error(
                "Host %s: Device not active error with redundancy state %s and peer redundancy state %s",
                self.host,
                redundancy_state,
                peer_redundancy_state,
            )
            raise DeviceNotActiveError(self.host, redundancy_state, peer_redundancy_state)

        log.debug("Host %s: Device is active.", self.host)
        return True

    @property
    def connected(self):  # noqa: D401
        """
        Get connection status of the device.

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

        log.debug("Host %s: Device enabled.", self.host)

    @property
    def uptime(self):
        """Get uptime from device.

        Returns:
            int: Uptime in seconds.
        """
        if self._uptime is None:
            version_data = self._raw_version_data()
            uptime_full_string = version_data["uptime"]
            self._uptime = self._uptime_to_seconds(uptime_full_string)

        log.debug("Host %s: Uptime %s", self.host, self._uptime)
        return self._uptime

    @property
    def uptime_string(self):
        """Get uptime in format dd:hh:mm.

        Returns:
            str: Uptime of device.
        """
        if self._uptime_string is None:
            version_data = self._raw_version_data()
            uptime_full_string = version_data["uptime"]
            self._uptime_string = self._uptime_to_string(uptime_full_string)

        return self._uptime_string

    @property
    def hostname(self):
        """Get hostname of device.

        Returns:
            str: Hostname of device.
        """
        match = re.search(r"hostname\s+(\S+)", self.show("show run hostname"))
        hostname = match.group(1) if match else None
        if self._hostname is None:
            self._hostname = hostname

        log.debug("Host %s: Hostname {self._hostname}", self.host)
        return self._hostname

    @property
    def interfaces(self):
        """
        Get list of interfaces on device.

        Returns:
            list: List of interfaces on device.
        """
        if self._interfaces is None:
            self._interfaces = list(x["interface"] for x in self._interfaces_detailed_list())

        log.debug("Host %s: Interfaces %s", self.host, self._interfaces)
        return self._interfaces

    @property
    def fqdn(self):
        """Get fully qualified domain name.

        Returns:
            str: Fully qualified domain name or ``N/A`` if not defined.
        """
        if self._fqdn is None:
            self._fqdn = "N/A"

        log.debug("Host %s: FQDN %s", self.host, self._fqdn)
        return self._fqdn

    @property
    def model(self):
        """Get the device model.

        Returns:
            str: Device model.
        """
        version_data = self._raw_version_data()

        if self._model is None:
            self._model = version_data["hardware"]

        log.debug("Host %s: Model %s", self.host, self._model)
        return self._model

    @property
    def os_version(self):
        """Get os version on device.

        Returns:
            str: OS version on device.
        """
        version_data = self._raw_version_data()
        if self._os_version is None:
            self._os_version = version_data["version"]

        log.debug("Host %s: OS version %s", self.host, self._os_version)
        return self._os_version

    @property
    def serial_number(self):
        """Get serial number of device.

        Returns:
            str: Serial number of device.
        """
        inventory_data = self._raw_inventory_data()
        log.debug("Host %s: Inventory data", inventory_data)
        if self._serial_number is None:
            self._serial_number = inventory_data[0]["sn"]

        log.debug("Host %s: Serial number %s", self.host, self._serial_number)
        return self._serial_number

    def file_copy(self, src, dest=None, file_system="disk0:", overwrite=False):
        """Copy file to device.

        Args:
            src (str): Source of file.
            dest (str, optional): Destination name for file. Defaults to None.
            file_system (str, optional): File system to copy file to. Defaults to None.

        Raises:
            SocketClosedError: Error raised if connection to device is closed.
            FileTransferError: Error in transferring file.
            FileTransferError: Error if unable to verify file was transferred successfully.
        """
        transfer_result = file_transfer(
            self.native,
            source_file=src,
            dest_file=dest,
            file_system=file_system,
            direction="put",
            overwrite_file=overwrite,
            verify_file=True,
        )
        if transfer_result.get("file_exists"):
            if overwrite:
                log.info(f"File {src} already exists on device. Overwriting.")
            else:
                raise FileTransferError("File already exists on device.")
        if not transfer_result.get("file_transfered"):
            raise FileTransferError("File transfer failed.")
        if not transfer_result.get("file_verified"):
            raise FileTransferError("File transfer validation failed.")

    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        """Copy Files when the remote file exists - Not Implemeted in this version.

        Args:
            src (_type_): _description_
            dest (_type_, optional): _description_. Defaults to None.

        Raises:
            NotImplementedError: _description_
        """
        raise NotImplementedError

    def install_os(self, image_name, install_mode=False, read_timeout=2000, **vendor_specifics):
        """Installs the prescribed Network OS, which must be present before issuing this command.

        Args:
            image_name (str): Name of the IOS image to boot into
            install_mode (bool, optional): Uses newer install method on devices. Defaults to False.
            read_timeout (int, optional): Netmiko timeout when waiting for device prompt. Default 30.

        Raises:
            OSInstallError: Unable to install OS Error type

        Returns:
            bool: False if no install is needed, true if the install completes successfully
        """
        raise NotImplementedError

    def is_active(self):
        """
        Determine if the current processor is the active processor.

        Returns:
            bool: True if the processor is active or does not support HA, else False.

        Example:
            >>> device = IOSXRDevice(**connection_args)
            >>> device.is_active()
            True
            >>>
        """
        self._redundancy_check()
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
            >>> device = IOSXRDevice(**connection_args)
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
            except:  # noqa E722  # pylint: disable=bare-except
                self._connected = False

        if not self.connected:
            self.native = ConnectHandler(
                device_type="cisco_xr",
                ip=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                read_timeout_override=self.read_timeout_override,
                secret=self.secret,
                verbose=False,
            )
            self._connected = True

        if confirm_active:
            self.confirm_is_active()

        log.debug("Host %s: Connection to controller was opened successfully.", self.host)

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
        log.warning("Peer node not implemented in IOS-XR")

        processor_redundancy_state = None

        log.debug("Host %s: Processor redundancy state %s.", self.host, processor_redundancy_state)
        return processor_redundancy_state

    def reboot(self, wait_for_reload=False, **kwargs):
        """Reboot device.

        Reload the controller or controller pair.

        Args:
            wait_for_reload: Whether or not reboot method should also run _wait_for_device_reboot(). Defaults to False.

        Raises:
            ReloadTimeoutError: When the device is still unreachable after the timeout period.
        """
        if kwargs.get("confirm"):
            log.warning("Passing 'confirm' to reboot method is deprecated.")

        try:
            first_response = self.native.send_command_timing("reload")

            if "System configuration" in first_response:
                self.native.send_command_timing("no")

            try:
                self.native.send_command_timing("\n", read_timeout=10)
                self.native.send_command_timing("\n", read_timeout=10)
            except ReadTimeout as expected_exception:
                log.info("Host %s: Device rebooted.", self.host)
                log.info("Hit expected exception during reload: %s", expected_exception.__class__)
            if wait_for_reload:
                time.sleep(35)  # XR7 has 30 second delay in rebooting
                self._wait_for_device_reboot(**kwargs)
        except Exception as err:  # pylint: disable=broad-exception-caught
            log.error(err)
            log.error(err.__class__)

    @property
    def redundancy_mode(self):
        """
        Get operating redundancy mode of the device.

        Returns:
            str: The redundancy mode the device is operating in.
                If the command is not supported, then "n/a" is returned.

        Example:
            >>> device = IOSDevice(**connection_args)
            >>> device.redundancy_mode
            'stateful switchover'
            >>>
        """
        self._redundancy_check()
        # log.debug("Host %s: Redundancy mode is %s.", self.host, self.redundancy_mode)
        return self._redundancy_mode

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
        self._redundancy_check()
        return self._redundancy_state

    def rollback(self, rollback_to):
        """Rollback configuration to file on disk0:.

        Args:
            rollback_to (str): Name of the file to rollback to.

        Raises:
            RollbackError: Error if unable to rollback to configuration.
        """
        try:
            self.native.config_mode("configure")
            output = self.native.send_command(f"load disk0:/{rollback_to}")
            if "Loading" not in output:
                raise CommandError(f"load disk0:/{rollback_to}", f"{output}")
            self.native.commit()
            log.info("Host %s: Rollback to %s.", self.host, rollback_to)
        except CommandError:
            log.error("Host %s: Rollback unsuccessful. %s may not exist.", self.host, rollback_to)
            raise RollbackError(f"Rollback unsuccessful. {rollback_to} may not exist.")
        except Exception as e:
            log.error("Host %s: Rollback failed.", self.host)
            raise RollbackError(f"Rollback failed. Error: {e}")

    @property
    def running_config(self):
        """Get running configuration.

        Returns:
            str: Output of ``show running-config``.
        """
        log.debug("Host %s: Show running config.", self.host)
        return self.show("show running-config")

    def backup_to_disk(self, path="disk0:/backup-config"):
        """Backup running configuration to disk.

        Args:
            path (str, optional): Path of file to save running configuration. Defaults to disk0 and file "backup-config".

        Returns:
            bool: True if save is succesfull.
        """
        command = f"copy running-config {path}"
        # Changed to send_command_timing to not require a direct prompt return.
        self.native.send_command_timing(command)
        # If the user has enabled 'file prompt quiet' which dose not require any confirmation or feedback.
        # This will send return without requiring an OK.
        # Send a return to pass the [OK]? message - Increase read_timeout for looking for response.
        self.native.send_command_timing("\n", read_timeout=200)
        # Confirm that we have a valid prompt again before returning.
        self.native.find_prompt()
        log.debug("Host %s: Copy running config to path  %s.", self.host, path)
        return True

    def backup_running_config(self, filename=None):
        """Save a local copy of the running config."""
        raise NotImplementedError

    @property
    def startup_config(self):
        """Get startup configuration.

        Returns:
            str: Startup configuration.
        """
        return self.running_config

    def show(self, command, expect_string=None, **netmiko_args):
        """Run command on device.

        Args:
            command (str): Command to be ran.
            expect_string (str, optional): Expected string from command output. Defaults to None.

        Returns:
            str: Output of command.
        """
        self.enable()
        if isinstance(command, list):
            responses = []
            entered_commands = []
            for command_instance in command:
                entered_commands.append(command_instance)
                try:
                    responses.append(self._send_command(command_instance))
                except CommandError as e:
                    raise CommandListError(entered_commands, command_instance, e.cli_error_msg)

            return responses
        return self._send_command(command, expect_string=expect_string, **netmiko_args)


class RebootSignal(NTCError):  # noqa: D101
    """RebootSignal."""

    pass  # pylint: disable=unnecessary-pass
