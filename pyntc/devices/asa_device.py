"""Module for using a Cisco ASA device over SSH.
"""

import os
import re
import signal
import time
import warnings
from collections import Counter

from netmiko import ConnectHandler
from netmiko import FileTransfer

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


RE_SHOW_FAILOVER_GROUPS = re.compile(r"Group\s+\d+\s+State:\s+(.+?)\s*$", re.M)
RE_SHOW_FAILOVER_STATE = re.compile(r"(?:Primary|Secondary)\s+-\s+(.+?)\s*$", re.M)


@fix_docs
class ASADevice(BaseDevice):
    """Cisco ASA Device Implementation."""

    vendor = "cisco"
    active_redundancy_states = {None, "active"}

    def __init__(self, host, username, password, secret="", port=22, **kwargs):
        super().__init__(host, username, password, device_type="cisco_asa_ssh")

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
            # TODO: Get proper hostname

            raise FileSystemNotFoundError(hostname=self.host, command="dir")
        return file_system

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show version")
        if re.search(image_name, version_data):
            return True

        return False

    def _interfaces_detailed_list(self):
        ip_int = self.show("show interface")
        ip_int_data = get_structured_data("cisco_asa_show_interface.template", ip_int)

        return ip_int_data

    def _raw_version_data(self):
        show_version_out = self.show("show version")
        try:
            version_data = get_structured_data("cisco_asa_show_version.template", show_version_out)[0]
            return version_data
        except IndexError:
            return {}

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
            except:  # noqa E722 # nosec
                pass

        # TODO: Get proper hostname parameter
        raise RebootTimeoutError(hostname=self.host, wait_time=timeout)

    def backup_running_config(self, filename):
        with open(filename, "w") as f:
            f.write(self.running_config)

    @property
    def boot_options(self):
        show_boot_out = self.show("show boot | i BOOT variable")
        # Improve regex to get only the first boot $var in the sequence!
        boot_path_regex = r"Current BOOT variable = (\S+):\/(\S+)"

        match = re.search(boot_path_regex, show_boot_out)
        if match:
            boot_image = match.group(2)
        else:
            boot_image = None

        return dict(sys=boot_image)

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
        """Implement this once facts' re-factor is done. """
        return {}

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
        return False

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
            return None

        if "Failover On" in show_failover:
            peer_failover_data = show_failover.split("Other host:")[1]
            show_failover_groups = RE_SHOW_FAILOVER_GROUPS.findall(peer_failover_data)
            if not show_failover_groups:
                re_show_failover_peer_state = RE_SHOW_FAILOVER_STATE.search(peer_failover_data)
                peer_redundancy_state = re_show_failover_peer_state.group(1)
            else:
                if "Active" in show_failover_groups:
                    peer_redundancy_state = "active"
                else:
                    peer_redundancy_state_counter = Counter(show_failover_groups)
                    peer_redundancy_state = peer_redundancy_state_counter.most_common()[0][0]
        else:
            peer_redundancy_state = "disabled"

        return peer_redundancy_state.lower()

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
            return None

        if "Failover On" in show_failover:
            failover_data = show_failover.split("Other host:")[0]
            show_failover_groups = RE_SHOW_FAILOVER_GROUPS.findall(failover_data)
            if not show_failover_groups:
                re_show_failover_state = RE_SHOW_FAILOVER_STATE.search(failover_data)
                redundancy_state = re_show_failover_state.group(1)
            else:
                if "Active" in show_failover_groups:
                    redundancy_state = "active"
                else:
                    redundancy_state_counter = Counter(show_failover_groups)
                    redundancy_state = redundancy_state_counter.most_common()[0][0]
        else:
            redundancy_state = "disabled"

        return redundancy_state.lower()

    def rollback(self, rollback_to):
        raise NotImplementedError

    @property
    def running_config(self):
        return self.show("show running-config")

    def save(self, filename="startup-config"):
        command = "copy running-config %s" % filename
        # Changed to send_command_timing to not require a direct prompt return.
        self.native.send_command_timing(command)
        # If the user has enabled 'file prompt quiet' which dose not require any confirmation or feedback.
        # This will send return without requiring an OK.
        # Send a return to pass the [OK]? message - Increase delay_factor for looking for response.
        self.native.send_command_timing("\n", delay_factor=2)
        # Confirm that we have a valid prompt again before returning.
        self.native.find_prompt()
        return True

    def set_boot_options(self, image_name, **vendor_specifics):
        current_boot = self.show("show running-config | inc ^boot system ")
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = self._get_file_system()

        file_system_files = self.show("dir {0}".format(file_system))
        if re.search(image_name, file_system_files) is None:
            raise NTCFileNotFoundError(
                # TODO: Update to use hostname
                hostname=self.host,
                file=image_name,
                dir=file_system,
            )

        current_images = current_boot.splitlines()
        commands_to_exec = ["no {0}".format(image) for image in current_images]
        commands_to_exec.append("boot system {0}/{1}".format(file_system, image_name))
        self.config_list(commands_to_exec)

        self.save()
        if self.boot_options["sys"] != image_name:
            raise CommandError(
                command="boot system {0}/{1}".format(file_system, image_name),
                message="Setting boot command did not yield expected results",
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
