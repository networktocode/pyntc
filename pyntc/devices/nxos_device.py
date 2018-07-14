"""Module for using an NXOX device over NX-API.
"""
import os

from pyntc.errors import CommandError, CommandListError
from pyntc.data_model.converters import strip_unicode
from .system_features.file_copy.base_file_copy import FileTransferError
from .base_device import BaseDevice, RollbackError, RebootTimerError, fix_docs

from pynxos.device import Device as NXOSNative
from pynxos.features.file_copy import FileTransferError as NXOSFileTransferError
from pynxos.errors import CLIError

NXOS_API_DEVICE_TYPE = 'cisco_nxos_nxapi'

@fix_docs
class NXOSDevice(BaseDevice):
    def __init__(self, host, username, password, transport='http', timeout=30, port=None, **kwargs):
        super(NXOSDevice, self).__init__(host, username, password, vendor='cisco', device_type=NXOS_API_DEVICE_TYPE)
        self.transport = transport
        self.timeout = timeout

        self.native = NXOSNative(host, username, password, transport=transport, timeout=timeout, port=port)

    def open(self):
        pass

    def close(self):
        pass

    def set_timeout(self, timeout):
        self.native.timeout = timeout

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

    def show(self, command, raw_text=False):
        try:
            return strip_unicode(self.native.show(command, raw_text=raw_text))
        except CLIError as e:
            raise CommandError(command, str(e))

    def show_list(self, commands, raw_text=False):
        try:
            return strip_unicode(self.native.show_list(commands, raw_text=raw_text))
        except CLIError as e:
            raise CommandListError(commands, e.command, str(e))

    def save(self, filename='startup-config'):
        return self.native.save(filename=filename)

    def file_copy_remote_exists(self, src, dest=None, file_system='bootflash:'):
        dest = dest or os.path.basename(src)
        return self.native.file_copy_remote_exists(src, dest, file_system=file_system)

    def file_copy(self, src, dest=None, file_system='bootflash:'):
        dest = dest or os.path.basename(src)
        try:
            return self.native.file_copy(src, dest, file_system=file_system)
        except NXOSFileTransferError as e:
            print(str(e))
            raise FileTransferError

    def reboot(self, confirm=False, timer=0):
        if timer != 0:
            raise RebootTimerError(self.device_type)

        self.native.reboot(confirm=confirm)

    def get_boot_options(self):
        return self.native.get_boot_options()

    def set_boot_options(self, image_name, kickstart=None, **vendor_specifics):
        return self.native.set_boot_options(image_name, kickstart=kickstart)

    def checkpoint(self, filename):
        return self.native.checkpoint(filename)

    def rollback(self, filename):
        try:
            self.native.rollback(filename)
        except CLIError:
            raise RollbackError('Rollback unsuccessful, %s may not exist.' % filename)

    def backup_running_config(self, filename):
        self.native.backup_running_config(filename)

    @property
    def facts(self):
        if hasattr(self, '_facts'):
            return self._facts

        facts = strip_unicode(self.native.facts)
        facts['vendor'] = self.vendor

        self._facts = facts
        return self._facts

    @property
    def running_config(self):
        return self.native.running_config

    @property
    def startup_config(self):
        return self.show('show startup-config', raw_text=True)
