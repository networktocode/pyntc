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


# noinspection PyProtectedMember
@fix_docs
class NXOSDevice(BaseDevice):
    def __init__(self, host, username, password, transport='http', timeout=30, port=None):
        super(NXOSDevice, self).__init__(host, username, password, vendor='cisco', device_type='cisco_nxos_nxapi')
        self.transport = transport
        self._timeout = timeout
        self.native = NXOSNative(host, username, password, transport=transport, timeout=timeout, port=port)

    def backup_running_config(self, filename):
        self.native.backup_running_config(filename)

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
    def facts(self):
        if self._facts is None:
            # TODO: Fix pynxos to properly handle property; currently unable to refresh fact data
            self._facts = self.native._get_show_version_facts()
            self._facts['interfaces'] = self.native._get_interface_list()
            self._facts['vlans'] = self.native._get_vlan_list()
            self._facts['fqdn'] = 'N/A'

            facts = strip_unicode(self._facts)
            facts['vendor'] = self.vendor

        return self._facts

    def get_boot_options(self):
        return self.native.get_boot_options()

    def file_copy(self, src, dest=None, file_system='bootflash:'):
        dest = dest or os.path.basename(src)
        try:
            return self.native.file_copy(src, dest, file_system=file_system)
        except NXOSFileTransferError as e:
            print(str(e))
            raise FileTransferError

    def file_copy_remote_exists(self, src, dest=None, file_system='bootflash:'):
        dest = dest or os.path.basename(src)
        return self.native.file_copy_remote_exists(src, dest, file_system=file_system)

    def install_os(self, image_name, **vendor_specifics):
        kickstart = vendor_specifics.get('kickstart')
        self.set_boot_options(image_name, kickstart=kickstart)

    def open(self):
        pass

    def reboot(self, timer=0):
        if timer != 0:
            raise RebootTimerError(self.device_type)

        self.native.reboot(confirm=True)

    def rollback(self, filename):
        try:
            self.native.rollback(filename)
        except CLIError:
            raise RollbackError('Rollback unsuccessful, %s may not exist.' % filename)

    @property
    def running_config(self):
        if self._running_config is None:
            self._running_config = self.native.running_config

        return self._running_config

    def save(self, filename='startup-config'):
        return self.native.save(filename=filename)

    def set_boot_options(self, image_name, **vendor_specifics):
        # TODO: Update pynxos class to use install_os name
        kickstart = vendor_specifics.get('kickstart')
        return self.native.set_boot_options(image_name, kickstart=kickstart)

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, seconds):
        self._timeout = seconds
        self.native.timeout = seconds

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

    @property
    def startup_config(self):
        if self._startup_config is None:
            self._startup_config = self.show('show startup-config', raw_text=True)

        return self._startup_config
