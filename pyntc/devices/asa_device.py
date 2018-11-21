"""Module for using a Cisco ASA device over SSH.
"""

import os
import re
import signal
import time

from netmiko import ConnectHandler
from netmiko import FileTransfer

from pyntc.templates import get_structured_data
from .base_device import BaseDevice, fix_docs
from .system_features.file_copy.base_file_copy import FileTransferError
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    NTCError,
    NTCFileNotFoundError,
    RebootTimeoutError,
    OSInstallError,
)

@fix_docs
class ASADevice(BaseDevice):
    def __init__(self, host, username, password, secret="", port=22, **kwargs):
        super(ASADevice, self).__init__(host, username, password, vendor="cisco", device_type="cisco_asa_ssh")

        self.native = None
        self.host = host
        self.username = username
        self.password = password
        self.secret = secret
        self.port = int(port)
        self.global_delay_factor = kwargs.get("global_delay_factor", 1)
        self.delay_factor = kwargs.get("delay_factor", 1)
        self._connected = False
        self.open()

    def _enable(self):
        self.native.exit_config_mode()
        if not self.native.check_enable_mode():
            self.native.enable()

    def _enter_config(self):
        self._enable()
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
            return file_system
        except AttributeError:
            # TODO: Get proper hostname
            raise FileSystemNotFoundError(hostname=self.host, command="dir")

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show version")
        if re.search(image_name, version_data):
            return True

        return False

    def _interfaces_detailed_list(self):
        ip_int = self.show("show interface")
        ip_int_data = get_structured_data("cisco_asa_show_interface.template", ip_int)

        return ip_int_data

    def _is_catalyst(self):
        return self.facts["model"].startswith("WS-")

    def _raw_version_data(self):
        show_version_out = self.show("show version")
        try:
            version_data = get_structured_data("cisco_asa_show_version.template", show_version_out)[0]
            return version_data
        except IndexError:
            return {}

    def _send_command(self, command, expect=False, expect_string=""):
        if expect:
            if expect_string:
                response = self.native.send_command_expect(command, expect_string=expect_string)
            else:
                response = self.native.send_command_expect(command)
        else:
            response = self.native.send_command_timing(command)

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
            except:
                pass

        # TODO: Get proper hostname parameter
        raise RebootTimeoutError(hostname=self.host, wait_time=timeout)

    def backup_running_config(self, filename):
        with open(filename, "w") as f:
            f.write(self.running_config)

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

    @property
    def facts(self):
        """Implement this once facts' re-factor is done. """
        return {}

    def file_copy(self, src, dest=None, file_system=None):
        self._enable()
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
            except:
                raise FileTransferError
            finally:
                fc.close_scp_chan()

            if not self.file_copy_remote_exists(src, dest, file_system):
                raise FileTransferError(
                    message="Attempted file copy, but could not validate file existed after transfer"
                )

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, file_system=None):
        self._enable()
        if file_system is None:
            file_system = self._get_file_system()

        fc = self._file_copy_instance(src, dest, file_system=file_system)
        if fc.check_file_exists() and fc.compare_md5():
            return True
        return False

    def get_boot_options(self):
        show_boot_out = self.show("show boot | i BOOT variable")
        # Improve regex to get only the first boot $var in the sequence!
        boot_path_regex = r"Current BOOT variable = (\S+):\/(\S+)"

        match = re.search(boot_path_regex, show_boot_out)
        if match:
            boot_image = match.group(2)
        else:
            boot_image = None

        return dict(sys=boot_image)

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

    def open(self):
        if self._connected:
            try:
                self.native.find_prompt()
            except:
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

    def rollback(self, rollback_to):
        raise NotImplementedError

    @property
    def running_config(self):
        return self.show("show running-config", expect=True)

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
        if self.get_boot_options()["sys"] != image_name:
            raise CommandError(
                command="boot system {0}/{1}".format(file_system, image_name),
                message="Setting boot command did not yield expected results",
            )

    def show(self, command, expect=False, expect_string=""):
        self._enable()
        return self._send_command(command, expect=expect, expect_string=expect_string)

    def show_list(self, commands):
        self._enable()

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
