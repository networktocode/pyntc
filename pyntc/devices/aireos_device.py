"""Module for using a Cisco WLC/AIREOS device over SSH."""

import os
import re
import time
import signal
import warnings

from netmiko import ConnectHandler

from .base_device import BaseDevice, fix_docs
from pyntc.errors import (
    NTCError,
    CommandError,
    OSInstallError,
    WLANEnableError,
    CommandListError,
    WLANDisableError,
    FileTransferError,
    RebootTimeoutError,
    DeviceNotActiveError,
    NTCFileNotFoundError,
    PeerFailedToFormError,
)


RE_FILENAME_FIND_VERSION = re.compile(r"^.+?(?P<version>\d+(?:-|_)\d+(?:-|_)\d+(?:-|_)\d+)\.", re.M)
RE_AP_IMAGE_COUNT = re.compile(r"^[Tt]otal\s+number\s+of\s+APs\.+\s+(?P<count>\d+)\s*$", re.M)
RE_AP_IMAGE_DOWNLOADED = re.compile(r"^\s*[Cc]ompleted\s+[Pp]redownloading\.+\s+(?P<downloaded>\d+)\s*$", re.M)
RE_AP_IMAGE_UNSUPPORTED = re.compile(r"^\s*[Nn]ot\s+[Ss]upported\.+\s+(?P<unsupported>\d+)\s*$", re.M)
RE_AP_IMAGE_FAILED = re.compile(r"^\s*[Ff]ailed\s+to\s+[Pp]redownload\.+\s+(?P<failed>\d+)\s*$", re.M)
RE_AP_BOOT_OPTIONS = re.compile(
    r"^(?P<name>.+?)\s+(?P<primary>(?:\d+\.){3}\d+)\s+(?P<backup>(?:\d+\.){3}\d+)\s+(?P<status>\S+).+$",
    re.M,
)
RE_PEER_REDUNDANCY_STATE = re.compile(r"^\s*Peer\s+State\s*=\s*(.+?)\s*$", re.M)
RE_REDUNDANCY_STATE = re.compile(r"^\s*Local\s+State\s*=\s*(.+?)\s*$", re.M)
RE_WLANS = re.compile(
    r"^(?P<wlan_id>\d+)\s+(?P<profile>\S+)\s*/\s+(?P<ssid>\S+)\s+(?P<status>\S+)\s+(?P<interface>.+?)\s*\S+\s*$", re.M
)


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
    version = re.sub("-|_", ".", version_string)
    return version


@fix_docs
class AIREOSDevice(BaseDevice):
    """Cisco AIREOS Device Implementation."""

    vendor = "cisco"
    active_redundancy_states = {None, "active"}

    def __init__(self, host, username, password, secret="", port=22, confirm_active=True, **kwargs):
        """
        PyNTC Device implementation for Cisco WLC.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            secret (str): The password to escalate privilege on the device.
            port (int): The port to use to establish the connection.
            confirm_active (bool): Determines if device's high availability state should be validated before leaving connection open.
        """
        super().__init__(host, username, password, device_type="cisco_aireos_ssh")
        self.native = None
        self.secret = secret
        self.port = int(port)
        self.global_delay_factor = kwargs.get("global_delay_factor", 1)
        self.delay_factor = kwargs.get("delay_factor", 1)
        self._connected = False
        self.open(confirm_active=confirm_active)

    def _ap_images_match_expected(self, image_option, image, ap_boot_options=None):
        """
        Test that all AP images have the ``image_option`` matching ``image``.

        Args:
            image_option (str): The boot_option dict key ("primary", "backup") to validate.
            image (str): The image that the ``image_option`` should match.
            ap_boot_options (dict): The results from ``self.ap_boot_options``.

        Returns:
            bool: True if all APs have ``image_option`` equal to ``image``, else False.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.ap_boot_options
            {
                'ap1': {'primary': '8.10.105.0', 'secondary': '8.10.103.0'},
                'ap2': {'primary': '8.10.105.0', 'secondary': '8.10.103.0'},
            }
            >>> device._ap_images_match_expected("primary", "8.10.105.0")
            True
            >>>
        """
        if ap_boot_options is None:
            ap_boot_options = self.ap_boot_options

        return all([boot_option[image_option] == image for boot_option in ap_boot_options.values()])

    def _check_command_output_for_errors(self, command, command_response):
        """
        Check response from device to see if an error was reported.

        Args:
            command (str): The command that was sent to the device.

        Raises:
            CommandError: When ``command_response`` reports an error in sending ``command``.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> command = "show version"
            >>> command_response = "output from show version"
            >>> device._check_command_output_for_errors(command, command_response)
            >>> command = "invalid command"
            >>> command_response = "Incorrect Usage: invalid command"
            >>> device._check_command_output_for_errors(command, command_resposne)
            CommandError: ...
            >>>
        """
        if "Incorrect usage" in command_response or "Error:" in command_response:
            raise CommandError(command, command_response)

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

    def _send_command(self, command, expect_string=None, **kwargs):
        """
        Send single command to device.

        Args:
            command (str): The command to send to the device.
            expect_string (str): The expected prompt after running the command.

        Kwargs:
            Any argument supported by Netmiko's ``send_command_timing`` method.

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
        if expect_string is None:
            response = self.native.send_command_timing(command, **kwargs)
        else:
            response = self.native.send_command(command, expect_string=expect_string, **kwargs)

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

    def _wait_for_ap_image_download(self, timeout=3600):
        """
        Wait for all APs have completed downloading the image.

        Args:
            timeout (int): The max time to wait for all APs to download the image.

        Raises:
            FileTransferError: When an AP is unable to properly retrieve the image or ``timeout`` is reached.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.ap_image_stats()
            {
                "count": 2,
                "downloaded": 0,
                "unsupported": 0,
                "failed": 0,
            }
            >>> device._wait_for_ap_image_download()
            >>> device.ap_image_stats()
            {
                "count": 2,
                "downloaded": 2,
                "unsupported": 0,
                "failed": 0,
            }
            >>>

        TODO:
            Change timeout to be a multiplier for number of APs attached to controller
        """
        start = time.time()
        ap_image_stats = self.ap_image_stats
        ap_count = ap_image_stats["count"]
        downloaded = 0
        while downloaded < ap_count:
            ap_image_stats = self.ap_image_stats
            downloaded = ap_image_stats["downloaded"]
            unsupported = ap_image_stats["unsupported"]
            failed = ap_image_stats["failed"]
            # TODO: When adding logging, send log message of current stats
            if unsupported or failed:
                raise FileTransferError(
                    "Failed transferring image to AP\n" f"Unsupported: {unsupported}\n" f"Failed: {failed}\n"
                )
            elapsed_time = time.time() - start
            if elapsed_time > timeout:
                raise FileTransferError(
                    "Failed waiting for AP image to be transferred to all devices:\n"
                    f"Total: {ap_count}\nDownloaded: {downloaded}"
                )

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
            except:  # noqa E722 # nosec
                pass

        # TODO: Get proper hostname parameter
        raise RebootTimeoutError(hostname=self.host, wait_time=timeout)

    def _wait_for_peer_to_form(self, redundancy_state, timeout=300):
        """
        Wait for device redundancy state to form properly.

        Args:
            redundancy_state (str): The desired redundancy state between the system and its peer.
            timeout (int): The max time to wait for peer to form before considering it unable to form.

        Returns:
            None: Nothing is returned when redundancy state reaches ``redundancy_state``.

        Raises:
            PeerFailedToFormError: When the ``timeout`` is reached before ``redundancy_state`` is reached.

        Example:
            >>> device = AIREOSDevice(**connection_args):
            >>> device.peer_redundancy_state
            'standby hot'
            >>> device.reboot()
            >>> device._wait_for_peer_to_form("standby hot")
            >>>
        """
        start = time.time()
        while time.time() - start < timeout:
            current_state = self.peer_redundancy_state
            if current_state == redundancy_state:
                return

        raise PeerFailedToFormError(hostname=self.host, desired_state=redundancy_state, current_state=current_state)

    @property
    def ap_boot_options(self):
        """
        Boot Options for all APs associated with the controller.

        Returns:
            dict: The name of each AP are the keys, and the values are the primary and backup values.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.ap_boot_options
            {
                'ap1': {
                    'backup': '8.8.125.0',
                    'primary': '8.9.110.0',
                    'status': 'complete'
                },
                'ap2': {
                    'backup': '8.8.125.0',
                    'primary': '8.9.110.0',
                    'status': 'complete'
                },
            }
            >>>
        """
        ap_images = self.show("show ap image all")
        ap_boot_options = RE_AP_BOOT_OPTIONS.finditer(ap_images)
        boot_options_by_ap = {
            ap["name"]: {
                "primary": ap.group("primary"),
                "backup": ap.group("backup"),
                "status": ap.group("status").lower(),
            }
            for ap in ap_boot_options
        }
        return boot_options_by_ap

    @property
    def ap_image_stats(self):
        """
        The stats of downloading the the image to all APs.

        Returns:
            dict: The AP count, and the downloaded, unsupported, and failed APs.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.ap_image_stats
            {
                'count': 2,
                'downloaded': 2,
                'unsupported': 0,
                'failed': 0
            }
            >>>
        """
        ap_images = self.show("show ap image all")
        count = RE_AP_IMAGE_COUNT.search(ap_images).group(1)
        downloaded = RE_AP_IMAGE_DOWNLOADED.search(ap_images).group(1)
        unsupported = RE_AP_IMAGE_UNSUPPORTED.search(ap_images).group(1)
        failed = RE_AP_IMAGE_FAILED.search(ap_images).group(1)
        return {
            "count": int(count),
            "downloaded": int(downloaded),
            "unsupported": int(unsupported),
            "failed": int(failed),
        }

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
            **netmiko_args: Any argument supported by ``netmiko.base_connection.BaseConnection.send_config_set``.

        Returns:
            str: When ``command`` is a str, the config session input and ouput from sending ``command``.
            list: When ``command`` is a list, the config session input and ouput from sending ``command``.

        Raises:
            TypeError: When sending an argument in ``**netmiko_args`` that is not supported.
            CommandError: When ``command`` is a str and its results report an error.
            CommandListError: When ``command`` is a list and one of the commands reports an error.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.config("boot primary")
            '(host) config>boot primary\n\n(host) config>'
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
            **netmiko_args: Any argument supported by ``netmiko.base_connection.BaseConnection.send_config_set``.

        Returns:
            list: Each command's input and ouput from sending the command in ``commands``.

        Raises:
            TypeError: When sending an argument in ``**netmiko_args`` that is not supported.
            CommandListError: When one of the commands reports an error on the device.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.config_list(["interface hostname virtual wlc1.site.com", "config interface vlan airway 20"])
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
            >>> device = AIREOSDevice(**connection_args)
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

    def disable_wlans(self, wlan_ids):
        """
        Disable all given WLAN IDs.

        The string `all` can be passed to disable all WLANs.
        Commands are sent to disable WLAN IDs that are not in `self.disabled_wlans`.
        If trying to disable `all` WLANS, then "all" will be sent,
        unless all WLANs in `self.wlans` are in `self.disabled_wlans`.

        Args:
            wlan_ids (str|list): List of WLAN IDs or `all`.

        Raises:
            WLANDisableError: When ``wlan_ids`` are not in `self.disabled_wlans` after configuration.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.disabled_wlans
            [2, 4, 8]
            >>> device.disable_wlans([1])
            >>> device.disabled_wlans
            [1, 2, 4, 8]
            >>> device.disable_wlans("all")
            [1, 2, 3, 4, 7, 8]
            >>>
        """
        if wlan_ids == "all":
            wlan_ids = ["all"]
            wlans_to_validate = set(self.wlans)
        else:
            wlans_to_validate = set(wlan_ids)

        disabled_wlans = self.disabled_wlans
        # Only send commands for enabled wlan ids
        if not wlans_to_validate.issubset(disabled_wlans):
            commands = [f"wlan disable {wlan}" for wlan in wlan_ids if wlan not in disabled_wlans]
            self.config(commands)

            post_disabled_wlans = self.disabled_wlans
            if not wlans_to_validate.issubset(post_disabled_wlans):
                desired_wlans = wlans_to_validate.union(disabled_wlans)
                raise WLANDisableError(self.host, desired_wlans, post_disabled_wlans)

    @property
    def disabled_wlans(self):
        """
        The IDs for all disabled WLANs.

        Returns:
            list: Disabled WLAN IDs.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.wlans
            {
                1: {'profile': 'wlan 1', 'ssid': 'wifi', 'status': 'enabled', 'interface': '1'},
                2: {'profile': 'wlan 2', 'ssid': 'corp', 'status': 'disabled', 'interface': '1'},
                3: {'profile': 'wlan 3', 'ssid': 'guest', 'status': 'enabled', 'interface': '1'},
                4: {'profile': 'wlan 4', 'ssid': 'test', 'status': 'disabled', 'interface': '1'},
                7: {'profile': 'wlan 7', 'ssid': 'internet', 'status': 'enabled', 'interface': '1'},
                8: {'profile': 'wlan 8', 'ssid': 'wifi-v', 'status': 'disabled', 'interface': '1'}
            }
            >>> device.disabled_wlans
            [2, 4, 8]
            >>>
        """
        disabled_wlans = [wlan_id for wlan_id, wlan_data in self.wlans.items() if wlan_data["status"] == "Disabled"]
        return disabled_wlans

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

    def enable_wlans(self, wlan_ids):
        """
        Enable all given WLAN IDs.

        The string `all` can be passed to enable all WLANs.
        Commands are sent to enable WLAN IDs that are not in `self.enabled_wlans`.
        If trying to enable `all` WLANS, then "all" will be sent,
        unless all WLANs in `self.wlans` are in `self.enabled_wlans`.

        Args:
            wlan_ids (str|list): List of WLAN IDs or `all`.

        Raises:
            WLANEnableError: When ``wlan_ids`` are not in `self.enabled_wlans` after configuration.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.enabled_wlans
            [1, 3, 7]
            >>> device.enable_wlans([2])
            >>> device.enabled_wlans
            [1, 2, 3, 7]
            >>> device.enable_wlans("all")
            >>> dev.enabled_wlans
            [1, 2, 3, 4, 7, 8]
            >>>
        """
        if wlan_ids == "all":
            wlan_ids = ["all"]
            wlans_to_validate = set(self.wlans)
        else:
            wlans_to_validate = set(wlan_ids)

        enabled_wlans = self.enabled_wlans
        # Only send commands for disabled wlan ids
        if not wlans_to_validate.issubset(enabled_wlans):
            commands = [f"wlan enable {wlan}" for wlan in wlan_ids if wlan not in enabled_wlans]
            self.config(commands)

            post_enabled_wlans = self.enabled_wlans
            if not wlans_to_validate.issubset(post_enabled_wlans):
                desired_wlans = wlans_to_validate.union(enabled_wlans)
                raise WLANEnableError(self.host, desired_wlans, post_enabled_wlans)

    @property
    def enabled_wlans(self):
        """
        The IDs for all enabled WLANs.

        Returns:
            list: Enabled WLAN IDs.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.wlans
            {
                1: {'profile': 'wlan 1', 'ssid': 'wifi', 'status': 'enabled', 'interface': '1'},
                2: {'profile': 'wlan 2', 'ssid': 'corp', 'status': 'disabled', 'interface': '1'},
                3: {'profile': 'wlan 3', 'ssid': 'guest', 'status': 'enabled', 'interface': '1'},
                4: {'profile': 'wlan 4', 'ssid': 'test', 'status': 'disabled', 'interface': '1'},
                7: {'profile': 'wlan 7', 'ssid': 'internet', 'status': 'enabled', 'interface': '1'},
                8: {'profile': 'wlan 8', 'ssid': 'wifi-v', 'status': 'disabled', 'interface': '1'}
            }
            >>> device.enabled_wlans
            [1, 3, 7]
            >>>
        """
        enabled_wlans = [wlan_id for wlan_id, wlan_data in self.wlans.items() if wlan_data["status"] == "Enabled"]
        return enabled_wlans

    @property
    def facts(self):
        raise NotImplementedError

    def file_copy(
        self,
        username,
        password,
        server,
        filepath,
        protocol="sftp",
        filetype="code",
        delay_factor=10,
    ):
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
            self.show(
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
        except CommandListError as error:
            raise FileTransferError(error.message)

        try:
            response = self.native.send_command_timing("transfer download start")
            if "Are you sure you want to start? (y/N)" in response:
                response = self.show("y", auto_find_prompt=False, delay_factor=delay_factor)
        except CommandError as error:
            raise FileTransferError(message=f"{FileTransferError.default_message}\n\n{error.message}")
        except:  # noqa E722
            raise FileTransferError

        if "File transfer is successful" not in response:
            raise FileTransferError(message=f"Did not find expected success message in response, found:\n{response}")

        return True

    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        raise NotImplementedError

    def install_os(self, image_name, controller="both", save_config=True, disable_wlans=None, **vendor_specifics):
        """
        Install an operating system on the controller.

        Args:
            image_name (str): The version to install on the device.
            controller (str): The controller(s) to reboot for install (only applies to HA device).
            save_config (bool): Whether the config should be saved to the device before reboot.
            disable_wlans (str|list): Which WLANs to disable/enable before/after upgrade. Default is None.
                To disable all WLANs, pass `"all"`. To disable select WLANs, pass a list of WLAN IDs.

        Returns:
            bool: True when the install is successful, False when the version is deemed to already be running.

        Raises:
            OSInstallError: When the device is not booted with the specified image after reload.
            RebootTimeoutError: When the device is unreachable longer than the reboot timeout value.
            WLANDisableError: When WLANs are not disabled properly before the upgrade.
            WLANEnableError: When WLANs are not enabled properly after the upgrade.

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
            peer_redundancy = self.peer_redundancy_state
            self.set_boot_options(image_name, **vendor_specifics)
            if disable_wlans is not None:
                self.disable_wlans(disable_wlans)
            self.reboot(controller=controller, save_config=save_config)
            self._wait_for_device_reboot(timeout=timeout)
            if disable_wlans is not None:
                self.enable_wlans(disable_wlans)
            if not self._image_booted(image_name):
                raise OSInstallError(hostname=self.host, desired_boot=image_name)
            try:
                self._wait_for_peer_to_form(peer_redundancy)
            except PeerFailedToFormError:
                raise OSInstallError(hostname=f"{self.host}-standby", desired_boot=f"{image_name}-{peer_redundancy}")

            return True

        return False

    def is_active(self):
        """
        Determine if the current processor is the active processor.

        Returns:
            bool: True if the processor is active or does not support HA, else False.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.is_active()
            True
            >>>
        """
        return self.redundancy_state in self.active_redundancy_states

    def open(self, confirm_active=True):
        """
        Open a connection to the controller.

        This method will close the connection if ``confirm_active`` is True and the device is not active.
        Devices that do not have high availibility are considred active.

        Args:
            confirm_active (bool): Determines if device's high availability state should be validated before leaving connection open.

        Raises:
            DeviceIsNotActiveError: When ``confirm_active`` is True, and the device high availabilit state is not active.

        Example:
            >>> device = AIREOSDevice(**connection_args)
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
                device_type="cisco_wlc",
                ip=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                global_delay_factor=self.global_delay_factor,
                secret=self.secret,
                verbose=False,
            )
            self._connected = True

        # This prevents open sessions from connecting to STANDBY WLC
        if confirm_active:
            self.confirm_is_active()

    @property
    def peer_redundancy_state(self):
        """
        Determine the redundancy state of the peer processor.

        Returns:
            str: The redundancy state of the peer processor.
            None: When the processor does not support redundancy.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.peer_redundancy_state
            'standby hot'
            >>>
        """
        try:
            show_redundancy = self.show("show redundancy summary")
        except CommandError:
            return None
        re_peer_redundancy_state = RE_PEER_REDUNDANCY_STATE.search(show_redundancy)
        peer_redundancy_state = re_peer_redundancy_state.group(1).lower()
        if peer_redundancy_state == "n/a":
            peer_redundancy_state = "disabled"
        return peer_redundancy_state

    def reboot(self, timer=0, controller="self", save_config=True, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            timer (int): The time to wait before reloading.
            controller (str): Which controller(s) to reboot (only applies to HA pairs).
            save_config (bool): Whether the configuration should be saved before reload.

        Raises:
            ReloadTimeoutError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.reboot()
            >>>
        """
        if kwargs.get("confirm"):
            warnings.warn("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

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
        Determine the redundancy state of the current processor.

        Returns:
            str: The redundancy state of the current processor.
            None: When the processor does not support redundancy.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.redundancy_state
            'active'
            >>>
        """
        try:
            show_redundancy = self.show("show redundancy summary")
        except CommandError:
            return None
        re_redundancy_state = RE_REDUNDANCY_STATE.search(show_redundancy)
        redundancy_state = re_redundancy_state.group(1).lower()
        if redundancy_state == "n/a":
            redundancy_state = "disabled"
        return redundancy_state

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
                command=boot_command,
                message="Setting boot command did not yield expected results",
            )

    def show(self, command, expect_string=None, **netmiko_args):
        """
        Send an operational command to the device.

        Args:
            command (str|list): The commands to send to the device.
            expect_string (str): The expected prompt after running the command.
            **netmiko_args: Any argument supported by ``netmiko.ConnectHandler.send_command``.

        Returns:
            str: When ``command`` is str, the data returned from the device.
            list: When ``command`` is list, the data returned from the device for each command.

        Raises:
            TypeError: When sending an argument in ``**netmiko_args`` that is not supported.
            CommandError: When ``command`` is str, and the returned data indicates the command failed.
            CommandListError: When ``command`` is list, and the return data indicates the command failed.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> sysinfo = device._send_command("show sysinfo")
            >>> print(sysinfo)
            Product Version.....8.2.170.0
            System Up Time......3 days 2 hrs 20 mins 30 sec
            ...
            >>> sysinfo = device._send_command(["show sysinfo"])
            >>> print(sysinfo[0])
            Product Version.....8.2.170.0
            System Up Time......3 days 2 hrs 20 mins 30 sec
            ...
            >>>
        """
        # TODO: Remove this when deprecating config_list method
        original_command_is_str = isinstance(command, str)

        if original_command_is_str:  # TODO: switch to isinstance(command, str) when removing above
            command = [command]

        entered_commands = []
        command_responses = []
        if expect_string is not None:
            netmiko_args["expect_string"] = expect_string

        try:
            for cmd in command:
                entered_commands.append(cmd)
                command_response = self.native.send_command(cmd, **netmiko_args)
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

        # TODO: Remove this when deprecating config_list method
        if original_command_is_str:
            return command_responses[0]

        return command_responses

    def show_list(self, commands, **netmiko_args):
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
        warnings.warn("show_list() is deprecated; use show.", DeprecationWarning)
        return self.show(commands, **netmiko_args)

    @property
    def startup_config(self):
        raise NotImplementedError

    def transfer_image_to_ap(self, image, timeout=None):
        """
        Transfer ``image`` file to all APs connected to the WLC.

        Args:
            image (str): The image that should be sent to the APs.
            timeout (int): The max time to wait for all APs to download the image.

        Returns:
            bool: True if AP images are transferred or swapped, False otherwise.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.ap_boot_options
            {
                'ap1': {
                    'backup': '8.8.125.0',
                    'primary': '8.9.110.0',
                    'status': 'complete'
                },
                'ap2': {
                    'backup': '8.8.125.0',
                    'primary': '8.9.110.0',
                    'status': 'complete'
                },
            }
            >>> device.transfer_image_to_ap("8.10.1.0")
            >>> device.ap_boot_options
            {
                'ap1': {
                    'backup': '8.9.110.0',
                    'primary': '8.10.1.0',
                    'status': 'complete'
                },
                'ap2': {
                    'backup': '8.9.110.0',
                    'primary': '8.10.1.0',
                    'status': 'complete'
                },
            }
            >>>
        """
        boot_options = ["primary", "backup"]
        ap_boot_options = self.ap_boot_options
        changed = False
        if self._ap_images_match_expected("primary", image, ap_boot_options):
            return changed

        if not any(self._ap_images_match_expected(option, image, ap_boot_options) for option in boot_options):
            changed = True
            download_image = None
            for option in boot_options:
                if self.boot_options[option] == image:
                    download_image = option
                    break
            if download_image is None:
                raise FileTransferError(f"Unable to find {image} on {self.host}")

            self.config(f"ap image predownload {option} all")
            self._wait_for_ap_image_download()

        counter = 0
        while counter < 3 and self._ap_images_match_expected("backup", image):
            counter += 1
            changed = True
            self.config("ap image swap all")
            # testing showed delay in reflecting changes when issuing `show ap image all`
            time.sleep(1)

        if not self._ap_images_match_expected("primary", image):
            raise FileTransferError(f"Unable to set all APs to use {image}")

        return changed

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

    @property
    def wlans(self):
        """
        All configured WLANs.

        Returns:
            dict: WLAN IDs mapped to their operational data.

        Example:
            >>> device = AIREOSDevice(**connection_args)
            >>> device.wlans
            {
                1: {'profile': 'wlan 1', 'ssid': 'wifi', 'status': 'enabled', 'interface': '1'},
                2: {'profile': 'wlan 2', 'ssid': 'corp', 'status': 'disabled', 'interface': '1'},
                3: {'profile': 'wlan 3', 'ssid': 'guest', 'status': 'enabled', 'interface': '1'},
                4: {'profile': 'wlan 4', 'ssid': 'test', 'status': 'disabled', 'interface': '1'},
                7: {'profile': 'wlan 7', 'ssid': 'internet', 'status': 'enabled', 'interface': '1'},
                8: {'profile': 'wlan 8', 'ssid': 'wifi-v', 'status': 'disabled', 'interface': '1'}
            }
            >>>
        """
        wlan_keys = ("profile", "ssid", "status", "interface")
        wlans = []
        show_wlan_summary_out = self.show("show wlan summary")
        re_wlans = RE_WLANS.finditer(show_wlan_summary_out)
        wlans = {int(wlan.group("wlan_id")): dict(zip(wlan_keys, wlan.groups()[1:])) for wlan in re_wlans}
        return wlans


class RebootSignal(NTCError):
    """Handles reboot interrupts."""

    pass
