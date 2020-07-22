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
        self.enable()
        self.native.config_mode()

    def _image_booted(self, image_name, **vendor_specifics):
        re_version = r"^Product\s+Version\s*\.+\s*(\S+)"
        sysinfo = self.show("show sysinfo")
        booted_image = re.search(re_version, sysinfo, re.M)
        if booted_image.group(1) == image_name:
            return True

        return False

    def _send_command(self, command, expect=False, expect_string=""):
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
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                return
            except:  # noqa E722
                pass

        # TODO: Get proper hostname parameter
        raise RebootTimeoutError(hostname=self.host, wait_time=timeout)

    @property
    def boot_options(self):
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
                self.native.exit_config_mode()
                raise CommandListError(entered_commands, command, e.cli_error_msg)
        self.native.exit_config_mode()

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value

    def close(self):
        if self.connected:
            self.native.disconnect()
            self.connected = False

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

    def file_copy(self, username, password, server, filepath, protocol="sftp", filetype="code"):
        self.enable()
        filedir, filename = os.path.split(filepath)
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
                    "transfer download start",
                ]
            )
        except:  # noqa E722
            raise FileTransferError

    def install_os(self, image_name, controller="both", save_config=True, **vendor_specifics):
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

            signal.alarm(15)
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
        ha = self.show("show redundancy summary")
        ha_mode = re.search(r"^\s*Redundancy\s+Mode\s*=\s*(.+?)\s*$", ha, re.M)
        return ha_mode.group(1).lower()

    @property
    def redundancy_state(self):
        ha = self.show("show redundancy summary")
        ha_state = re.search(r"^\s*Local\s+State\s*=\s*(.+?)\s*$", ha, re.M)
        if ha_state.group(1).lower() == "active":
            return True
        else:
            return False

    def save(self):
        self.native.save_config()
        return True

    def set_boot_options(self, image_name, **vendor_specifics):
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
        self.enable()
        return self._send_command(command, expect=expect, expect_string=expect_string)

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
    def uptime(self):
        days, hours, minutes = self._uptime_components()
        hours += days * 24
        minutes += hours * 60
        seconds = minutes * 60
        return seconds

    @property
    def uptime_string(self):
        days, hours, minutes = self._uptime_components()
        return "%02d:%02d:%02d:00" % (days, hours, minutes)


class RebootSignal(NTCError):
    pass
