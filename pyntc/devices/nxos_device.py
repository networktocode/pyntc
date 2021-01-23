"""Module for using an NXOX device over NX-API.
"""
import os
import re
import time
import warnings

from .base_device import BaseDevice, RollbackError, RebootTimerError, fix_docs
from pyntc.errors import (
    CommandError,
    OSInstallError,
    CommandListError,
    FileTransferError,
    RebootTimeoutError,
    NTCFileNotFoundError,
)

from pynxos.device import Device as NXOSNative
from pynxos.features.file_copy import FileTransferError as NXOSFileTransferError
from pynxos.errors import CLIError


@fix_docs
class NXOSDevice(BaseDevice):
    """Cisco NXOS Device Implementation."""

    vendor = "cisco"

    def __init__(self, host, username, password, transport="http", timeout=30, port=None, **kwargs):
        super().__init__(host, username, password, device_type="cisco_nxos_nxapi")
        self.transport = transport
        self.timeout = timeout
        self.native = NXOSNative(host, username, password, transport=transport, timeout=timeout, port=port)

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show version", raw_text=True)
        if re.search(image_name, version_data):
            return True

        return False

    def _wait_for_device_reboot(self, timeout=600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.refresh_facts()
                if self.uptime < 180:
                    return
            except:  # noqa E722 # nosec
                pass

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        self.native.backup_running_config(filename)

    @property
    def boot_options(self):
        return self.native.get_boot_options()

    def checkpoint(self, filename):
        return self.native.checkpoint(filename)

    def close(self):
        pass

    def config(self, command):
        try:
            self.native.config(command)
        except CLIError as e:
            raise CommandError(command, str(e))

    def config_list(self, commands):
        try:
            self.native.config_list(commands)
        except CLIError as e:
            raise CommandListError(commands, e.command, str(e))

    @property
    def uptime(self):
        if self._uptime is None:
            self._uptime = self.native.facts.get("uptime")

        return self._uptime

    @property
    def hostname(self):
        if self._hostname is None:
            self._hostname = self.native.facts.get("hostname")

        return self._hostname

    @property
    def interfaces(self):
        if self._interfaces is None:
            self._interfaces = self.native.facts.get("interfaces")

        return self._interfaces

    @property
    def vlans(self):
        if self._vlans is None:
            self._vlans = self.native.facts.get("vlans")

        return self._vlans

    @property
    def fqdn(self):
        if self._fqdn is None:
            self._fqdn = self.native.facts.get("fqdn")

        return self._fqdn

    @property
    def model(self):
        if self._model is None:
            self._model = self.native.facts.get("model")

        return self._model

    @property
    def os_version(self):
        if self._os_version is None:
            self._os_version = self.native.facts.get("os_version")

        return self._os_version

    @property
    def serial_number(self):
        if self._serial_number is None:
            self._serial_number = self.native.facts.get("serial_number")

        return self._serial_number

    def file_copy(self, src, dest=None, file_system="bootflash:"):
        if not self.file_copy_remote_exists(src, dest, file_system):
            dest = dest or os.path.basename(src)
            try:
                file_copy = self.native.file_copy(src, dest, file_system=file_system)
                if not self.file_copy_remote_exists(src, dest, file_system):
                    raise FileTransferError(
                        message="Attempted file copy, but could not validate file existed after transfer"
                    )
                return file_copy
            except NXOSFileTransferError as e:
                print(str(e))
                raise FileTransferError

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, file_system="bootflash:"):
        dest = dest or os.path.basename(src)
        return self.native.file_copy_remote_exists(src, dest, file_system=file_system)

    def install_os(self, image_name, **vendor_specifics):
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            self.set_boot_options(image_name, **vendor_specifics)
            self._wait_for_device_reboot(timeout=timeout)
            if not self._image_booted(image_name):
                raise OSInstallError(hostname=self.facts.get("hostname"), desired_boot=image_name)
            self.save()

            return True

        return False

    def open(self):
        pass

    def reboot(self, timer=0, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            timer (int, optional): The time to wait before reloading. Defaults to 0.

        Raises:
            RebootTimerError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = NXOSDevice(**connection_args)
            >>> device.reboot()
            >>
        """
        if kwargs.get("confirm"):
            warnings.warn("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        if timer != 0:
            raise RebootTimerError(self.device_type)

        self.native.reboot(confirm=True)

    def rollback(self, filename):
        try:
            self.native.rollback(filename)
        except CLIError:
            raise RollbackError("Rollback unsuccessful, %s may not exist." % filename)

    @property
    def running_config(self):
        return self.native.running_config

    def save(self, filename="startup-config"):
        return self.native.save(filename=filename)

    def set_boot_options(self, image_name, kickstart=None, **vendor_specifics):
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = "bootflash:"

        file_system_files = self.show("dir {0}".format(file_system), raw_text=True)
        if re.search(image_name, file_system_files) is None:
            raise NTCFileNotFoundError(hostname=self.hostname, file=image_name, dir=file_system)

        if kickstart is not None:
            if re.search(kickstart, file_system_files) is None:
                raise NTCFileNotFoundError(hostname=self.hostname, file=kickstart, dir=file_system)

            kickstart = file_system + kickstart

        image_name = file_system + image_name
        self.native.timeout = 300
        upgrade_result = self.native.set_boot_options(image_name, kickstart=kickstart)
        self.native.timeout = 30

        return upgrade_result

    def set_timeout(self, timeout):
        self.native.timeout = timeout

    def show(self, command, raw_text=False):
        try:
            return self.native.show(command, raw_text=raw_text)
        except CLIError as e:
            raise CommandError(command, str(e))

    def show_list(self, commands, raw_text=False):
        try:
            return self.native.show_list(commands, raw_text=raw_text)
        except CLIError as e:
            raise CommandListError(commands, e.command, str(e))

    @property
    def startup_config(self):
        return self.show("show startup-config", raw_text=True)
