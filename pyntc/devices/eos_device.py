"""Module for using an Arista EOS device over the eAPI.
"""

import re
import time

from pyntc.data_model.converters import convert_dict_by_key, convert_list_by_key, strip_unicode
from pyntc.data_model.key_maps import eos_key_maps
from .system_features.file_copy.eos_file_copy import EOSFileCopy
from .system_features.vlans.eos_vlans import EOSVlans
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

from pyeapi import connect as eos_connect
from pyeapi.client import Node as EOSNative
from pyeapi.eapilib import CommandError as EOSCommandError

from .system_features.file_copy.base_file_copy import FileTransferError


@fix_docs
class EOSDevice(BaseDevice):
    def __init__(self, host, username, password, transport="http", timeout=60, **kwargs):
        super(EOSDevice, self).__init__(host, username, password, vendor="arista", device_type="arista_eos_eapi")
        self.transport = transport
        self.timeout = timeout
        self.connection = eos_connect(transport, host=host, username=username, password=password, timeout=timeout)
        self.native = EOSNative(self.connection)

    def _get_file_system(self):
        """Determines the default file system or directory for device.

        Returns:
            str: The name of the default file system or directory for the device.

        Raises:
            FileSystemNotFound: When the module is unable to determine the default file system.
        """
        raw_data = self.show("dir", raw_text=True)
        try:
            file_system = re.match(r"\s*.*?(\S+:)", raw_data).group(1)
            return file_system
        except AttributeError:
            raise FileSystemNotFoundError(hostname=self.facts.get("hostname"), command="dir")

    def _get_interface_list(self):
        iface_detailed_list = self._interfaces_status_list()
        iface_list = sorted(list(x["interface"] for x in iface_detailed_list))

        return iface_list

    def _get_vlan_list(self):
        vlans = EOSVlans(self)
        vlan_list = vlans.get_list()

        return vlan_list

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show boot", raw_text=True)
        if re.search(image_name, version_data):
            return True

        return False

    def _interfaces_status_list(self):
        interfaces_list = []
        interfaces_status_dictionary = self.show("show interfaces status")["interfaceStatuses"]
        for key in interfaces_status_dictionary:
            interface_dictionary = interfaces_status_dictionary[key]
            interface_dictionary["interface"] = key
            interfaces_list.append(interface_dictionary)

        return convert_list_by_key(interfaces_list, eos_key_maps.INTERFACES_KM, fill_in=True, whitelist=["interface"])

    def _parse_response(self, response, raw_text):
        if raw_text:
            return list(x["result"]["output"] for x in response)
        else:
            return list(x["result"] for x in response)

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
            except:
                pass

        raise RebootTimeoutError(hostname=self.facts["hostname"], wait_time=timeout)

    def backup_running_config(self, filename):
        with open(filename, "w") as f:
            f.write(self.running_config)

    def checkpoint(self, checkpoint_file):
        self.show("copy running-config %s" % checkpoint_file)

    def close(self):
        pass

    def config(self, command):
        try:
            self.config_list([command])
        except CommandListError as e:
            raise CommandError(e.command, e.message)

    def config_list(self, commands):
        try:
            self.native.config(commands)
        except EOSCommandError as e:
            raise CommandListError(commands, e.commands[len(e.commands) - 1], e.message)

    @property
    def facts(self):
        if self._facts is None:
            sh_version_output = self.show("show version")
            self._facts = convert_dict_by_key(sh_version_output, eos_key_maps.BASIC_FACTS_KM)
            self._facts["vendor"] = self.vendor

            uptime = int(time.time() - sh_version_output["bootupTimestamp"])
            self._facts["uptime"] = uptime
            self._facts["uptime_string"] = self._uptime_to_string(uptime)

            sh_hostname_output = self.show("show hostname")
            self._facts.update(
                convert_dict_by_key(sh_hostname_output, {}, fill_in=True, whitelist=["hostname", "fqdn"])
            )

            self._facts["interfaces"] = self._get_interface_list()
            self._facts["vlans"] = self._get_vlan_list()

        return self._facts

    def file_copy(self, src, dest=None, **kwargs):
        if not self.file_copy_remote_exists(src, dest, **kwargs):
            fc = EOSFileCopy(self, src, dest)
            fc.send()

            if not self.file_copy_remote_exists(src, dest, **kwargs):
                raise FileTransferError(
                    message="Attempted file copy, but could not validate file existed after transfer"
                )

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        fc = EOSFileCopy(self, src, dest)
        if fc.remote_file_exists() and fc.already_transfered():
            return True
        return False

    def get_boot_options(self):
        image = self.show("show boot-config")["softwareImage"]
        image = image.replace("flash:", "")
        return dict(sys=image)

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
        pass

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
        except (CommandError, CommandListError):
            raise RollbackError("Rollback unsuccessful. %s may not exist." % rollback_to)

    @property
    def running_config(self):
        return self.show("show running-config", raw_text=True)

    def save(self, filename="startup-config"):
        self.show("copy running-config %s" % filename)
        return True

    def set_boot_options(self, image_name, **vendor_specifics):
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = self._get_file_system()

        file_system_files = self.show("dir {0}".format(file_system), raw_text=True)
        if re.search(image_name, file_system_files) is None:
            raise NTCFileNotFoundError(hostname=self.facts.get("hostname"), file=image_name, dir=file_system)

        self.show("install source {0}{1}".format(file_system, image_name))
        if self.get_boot_options()["sys"] != image_name:
            raise CommandError(
                command="install source {0}".format(image_name),
                message="Setting install source did not yield expected results",
            )

    def show(self, command, raw_text=False):
        try:
            response_list = self.show_list([command], raw_text=raw_text)
            return response_list[0]
        except CommandListError as e:
            raise CommandError(e.command, e.message)

    def show_list(self, commands, raw_text=False):
        if raw_text:
            encoding = "text"
        else:
            encoding = "json"

        try:
            return strip_unicode(
                self._parse_response(self.native.enable(commands, encoding=encoding), raw_text=raw_text)
            )
        except EOSCommandError as e:
            raise CommandListError(commands, e.commands[len(e.commands) - 1], e.message)

    @property
    def startup_config(self):
        return self.show("show startup-config", raw_text=True)


class RebootSignal(NTCError):
    pass
