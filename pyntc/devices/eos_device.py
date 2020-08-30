"""Module for using an Arista EOS device over the eAPI.
"""

import re
import time
import os

from netmiko import ConnectHandler
from netmiko import FileTransfer


from pyntc.utils import convert_dict_by_key, get_structured_data

from .base_device import BaseDevice, RollbackError, RebootTimerError, fix_docs
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    NTCError,
    NTCFileNotFoundError,
    RebootTimeoutError,
    OSInstallError,
)
from .system_features.file_copy.base_file_copy import FileTransferError


BASIC_FACTS_KM = {"model": "model", "image": "image", "serial_number": "serial_number"}
INTERFACES_KM = {
    "speed": "bandwidth",
    "duplex": "duplex",
    "vlan": ["vlanInformation", "vlanId"],
    "state": "linkStatus",
    "description": "description",
}


@fix_docs
class EOSDevice(BaseDevice):
    """Arista EOS Device Implementation."""

    vendor = "arista"

    def __init__(self, host, username, password, secret="", port=22, **kwargs):
        super().__init__(host, username, password, device_type="arista_eos_ssh")
        self.secret = secret
        self.port = int(port)
        self.global_delay_factor = kwargs.get("global_delay_factor", 1)
        self.delay_factor = kwargs.get("delay_factor", 1)
        self.native = None
        self._connected = False
        self.open()

    def _enter_config(self):
        self.enable()
        self.native.config_mode()

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

    def _get_interface_list(self):
        iface_detailed_list = self._interfaces_status_list()
        iface_list = sorted(list(x["name"] for x in iface_detailed_list))

        return iface_list

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show boot")
        if re.search(image_name, version_data):
            return True

        return False

    def _interfaces_status_list(self):
        show_interfaces_status_out = self.show("show interfaces status")
        try:
            interface_data = get_structured_data(
                "arista_eos_show_interfaces_status.template", show_interfaces_status_out
            )
        except IndexError:
            return {}

        return interface_data

    def _raw_version_data(self):
        show_version_out = self.show("show version")
        try:
            version_data = get_structured_data("arista_eos_show_version.template", show_version_out)[0]
        except IndexError:
            return {}

        return version_data

    def _show_vlan(self):
        show_vlan_out = self.show("show vlan")
        show_vlan_data = get_structured_data("arista_eos_show_vlan.template", show_vlan_out)

        return show_vlan_data

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

    def _uptime_to_string(self, uptime):
        days = uptime / (24 * 60 * 60)
        uptime = uptime % (24 * 60 * 60)

        hours = uptime / (60 * 60)
        uptime = uptime % (60 * 60)

        mins = uptime / 60
        uptime = uptime % 60

        seconds = uptime

        return "%02d:%02d:%02d:%02d" % (days, hours, mins, seconds)

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.show("show hostname")
                return
            except:  # noqa E722
                pass

        raise RebootTimeoutError(hostname=self.facts["hostname"], wait_time=timeout)

    def _file_copy_instance(self, src, dest=None, file_system="flash:"):
        if dest is None:
            dest = os.path.basename(src)

        fc = FileTransfer(self.native, src, dest, file_system=file_system)
        return fc

    def backup_running_config(self, filename):
        with open(filename, "w") as f:
            f.write(self.running_config)

    @property
    def boot_options(self):
        image = self.show("show boot-config")
        image = image.replace("flash:", "")
        return image

    def checkpoint(self, checkpoint_file):
        self.show("copy running-config %s" % checkpoint_file)

    def close(self):
        pass

    def config(self, command):
        self._enter_config()
        self._send_command(command)
        self.native.exit_config_mode()

    def config_list(self, commands):
        self._enter_config()
        entered_commands = []

        for cmd in commands:
            entered_commands.append(cmd)
            try:
                self._send_command(cmd)
            except CommandError as e:
                raise CommandListError(entered_commands, cmd, e.cli_error_msg)
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
            sh_version_output = self._raw_version_data()
            print(sh_version_output)
            self._facts = convert_dict_by_key(sh_version_output, BASIC_FACTS_KM)
            self._facts["vendor"] = self.vendor

            # uptime = int(time.time() - sh_version_output["bootupTimestamp"])
            # self._facts["uptime"] = uptime
            # self._facts["uptime_string"] = self._uptime_to_string(uptime)

            sh_hostname_output = self.show("show hostname")
            self._facts.update(
                convert_dict_by_key(sh_hostname_output, {}, fill_in=True, whitelist=["hostname", "fqdn"])
            )

            self._facts["interfaces"] = self._get_interface_list()
            self._facts["vlans"] = list(str(x["vlan_id"]) for x in self._show_vlan())

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
        # if not self.file_copy_remote_exists(src, dest, **kwargs):
        #     fc = EOSFileCopy(self, src, dest)
        #     fc.send()

        #     if not self.file_copy_remote_exists(src, dest, **kwargs):
        #         raise FileTransferError(
        #             message="Attempted file copy, but could not validate file existed after transfer"
        #         )

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

    def open(self):
        """Opens ssh connection with Netmiko ConnectHandler to be used with FileTransfer
        """
        if self._connected:
            try:
                self.native.find_prompt()
            except Exception:
                self._connected = False

        if not self._connected:
            self.native = ConnectHandler(
                device_type="arista_eos",
                ip=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                global_delay_factor=self.global_delay_factor,
                secret=self.secret,
                verbose=False,
            )
            self._connected = True

    def reboot(self, confirm=False, timer=0):
        if timer != 0:
            raise RebootTimerError(self.device_type)

        if confirm:
            self.show("reload now")
        else:
            print("Need to confirm reboot with confirm=True")

    def rollback(self, rollback_to):
        try:
            self.show("configure replace %s force" % rollback_to)
        except CommandError:
            raise RollbackError("Rollback unsuccessful. %s may not exist." % rollback_to)

    @property
    def running_config(self):
        return self.show("show running-config")

    def save(self, filename="startup-config"):
        """Seve startup configuration

        Args:
            filename (str, optional): filename to save. Defaults to "startup-config".

        Returns:
            bool: True if successful
        """
        self.native.send_command_timing("copy running-config %s" % filename)

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

        self.show("install source {0}{1}".format(file_system, image_name))
        if self.boot_options["sys"] != image_name:
            raise CommandError(
                command="install source {0}".format(image_name),
                message="Setting install source did not yield expected results",
            )

    def show(self, command, expect=False, expect_string=""):
        self.enable()
        return self._send_command(command, expect=expect, expect_string=expect_string)

    def show_list(self, commands):
        self.enable()

        responses = []
        entered_commands = []
        for cmd in commands:
            entered_commands.append(cmd)
            try:
                responses.append(self._send_command(cmd))
            except CommandError as e:
                raise CommandListError(entered_commands, cmd, e.cli_error_msg)

        return responses

    @property
    def startup_config(self):
        return self.show("show startup-config")


class RebootSignal(NTCError):
    pass
