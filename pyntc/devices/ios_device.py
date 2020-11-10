"""Module for using a Cisco IOS device over SSH.
"""

import signal
import os
import re
import time
import warnings

from netmiko import ConnectHandler
from netmiko import FileTransfer

from pyntc.utils import convert_dict_by_key, get_structured_data
from .system_features.file_copy.base_file_copy import FileTransferError
from .base_device import BaseDevice, RollbackError, fix_docs
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    NTCError,
    NTCFileNotFoundError,
    OSInstallError,
    RebootTimeoutError,
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


@fix_docs
class IOSDevice(BaseDevice):
    """Cisco IOS Device Implementation."""

    vendor = "cisco"
    active_redundancy_states = {None, "active"}

    def __init__(self, host, username, password, secret="", port=22, **kwargs):
        super().__init__(host, username, password, device_type="cisco_ios_ssh")

        self.native = None
        self.secret = secret
        self.port = int(port)
        self.global_delay_factor = kwargs.get("global_delay_factor", 1)
        self.delay_factor = kwargs.get("delay_factor", 1)
        self._connected = False
        self.open()

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
        raw_data = self.show("dir")
        try:
            file_system = re.match(r"\s*.*?(\S+:)", raw_data).group(1)
        except AttributeError:
            raise FileSystemNotFoundError(hostname=self.facts.get("hostname"), command="dir")

        return file_system

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show version")
        if re.search(image_name, version_data):
            return True

        return False

    def _interfaces_detailed_list(self):
        ip_int_br_out = self.show("show ip int br")
        ip_int_br_data = get_structured_data("cisco_ios_show_ip_int_brief.template", ip_int_br_out)

        return ip_int_br_data

    def _is_catalyst(self):
        return self.facts["model"].startswith("WS-")

    def _raw_version_data(self):
        show_version_out = self.show("show version")
        try:
            version_data = get_structured_data("cisco_ios_show_version.template", show_version_out)[0]
        except IndexError:
            return {}

        return version_data

    def _send_command(self, command, expect_string=None):
        if expect_string is None:
            response = self.native.send_command_timing(command)
        else:
            response = self.native.send_command(command, expect_string=expect_string)

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
                return
            except:  # noqa E722
                pass

        raise RebootTimeoutError(hostname=self.facts["hostname"], wait_time=timeout)

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
            boot_path = match.group(1)
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
        if self._connected:
            self.native.disconnect()
            self._connected = False

    def config(self, command):
        self._enter_config()
        self._send_command(command)
        self.native.exit_config_mode()

    def config_list(self, commands):
        self._enter_config()
        entered_commands = []
        for command in commands:
            entered_commands.append(command)
            try:
                self._send_command(command)
            except CommandError as e:
                raise CommandListError(entered_commands, command, e.cli_error_msg)
        self.native.exit_config_mode()

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
    def facts(self):
        if self._facts is None:
            version_data = self._raw_version_data()
            self._facts = convert_dict_by_key(version_data, BASIC_FACTS_KM)
            self._facts["vendor"] = self.vendor

            uptime_full_string = version_data["uptime"]
            self._facts["uptime"] = self._uptime_to_seconds(uptime_full_string)
            self._facts["uptime_string"] = self._uptime_to_string(uptime_full_string)
            self._facts["fqdn"] = "N/A"
            self._facts["interfaces"] = list(x["intf"] for x in self._interfaces_detailed_list())

            if self._facts["model"].startswith("WS"):
                self._facts["vlans"] = list(str(x["vlan_id"]) for x in self._show_vlan())
            else:
                self._facts["vlans"] = []

            # ios-specific facts
            self._facts[self.device_type] = {"config_register": version_data["config_register"]}

        return self._facts

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
            except:  # noqa E722
                raise FileTransferError
            finally:
                fc.close_scp_chan()

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

    def install_os(self, image_name, **vendor_specifics):
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            self.set_boot_options(image_name, **vendor_specifics)
            self.reboot(confirm=True)
            self._wait_for_device_reboot(timeout=timeout)
            if not self._image_booted(image_name):
                raise OSInstallError(hostname=self.facts.get("hostname"), desired_boot=image_name)

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
        if self.redundancy_state in self.active_redundancy_states:
            return True
        return False

    def open(self):
        if self._connected:
            try:
                self.native.find_prompt()
            except:  # noqa E722
                self._connected = False

        if not self._connected:
            self.native = ConnectHandler(
                device_type="cisco_ios",
                ip=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                global_delay_factor=self.global_delay_factor,
                secret=self.secret,
                verbose=False,
            )
            self._connected = True

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
        re_show_redundancy = RE_SHOW_REDUNDANCY.match(show_redundancy)
        processor_redundancy_info = re_show_redundancy.group("other")
        if processor_redundancy_info is not None:
            re_redundancy_state = RE_REDUNDANCY_STATE.search(processor_redundancy_info)
            processor_redundancy_state = re_redundancy_state.group(1).lower()
        else:
            processor_redundancy_state = "disabled"
        return processor_redundancy_state

    def reboot(self, timer=0, confirm=False):
        if confirm:

            def handler(signum, frame):
                raise RebootSignal("Interrupting after reload")

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
        else:
            print("Need to confirm reboot with confirm=True")

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
        re_show_redundancy = RE_SHOW_REDUNDANCY.match(show_redundancy)
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
        re_show_redundancy = RE_SHOW_REDUNDANCY.match(show_redundancy)
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
            raise NTCFileNotFoundError(hostname=self.facts.get("hostname"), file=image_name, dir=file_system)

        try:
            command = "boot system {0}/{1}".format(file_system, image_name)
            self.config_list(["no boot system", command])
        except CommandError:
            file_system = file_system.replace(":", "")
            command = "boot system {0} {1}".format(file_system, image_name)
            self.config_list(["no boot system", command])

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
