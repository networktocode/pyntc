"""Module for using an Arista EOS device over the eAPI.
"""

import time

from pyntc.errors import CommandError, CommandListError
from pyntc.data_model.converters import convert_dict_by_key, convert_list_by_key, strip_unicode
from pyntc.data_model.key_maps import eos_key_maps
from .system_features.file_copy.eos_file_copy import EOSFileCopy
from .system_features.vlans.eos_vlans import EOSVlans
from .base_device import BaseDevice, RollbackError, RebootTimerError, fix_docs

from pyeapi import connect as eos_connect
from pyeapi.client import Node as EOSNative
from pyeapi.eapilib import CommandError as EOSCommandError


@fix_docs
class EOSDevice(BaseDevice):

    def __init__(self, host, username, password, transport='http', timeout=60):
        super(EOSDevice, self).__init__(host, username, password, vendor='arista', device_type='arista_eos_eapi')
        self.transport = transport
        self.timeout = timeout
        self.connection = eos_connect(transport, host=host, username=username, password=password, timeout=timeout)
        self.native = EOSNative(self.connection)

    def _get_interface_list(self):
        iface_detailed_list = self._interfaces_status_list()
        iface_list = sorted(list(x['interface'] for x in iface_detailed_list))

        return iface_list

    def _get_vlan_list(self):
        vlans = EOSVlans(self)
        vlan_list = vlans.get_list()

        return vlan_list

    def _interfaces_status_list(self):
        interfaces_list = []
        interfaces_status_dictionary = self.show('show interfaces status')['interfaceStatuses']
        for key in interfaces_status_dictionary:
            interface_dictionary = interfaces_status_dictionary[key]
            interface_dictionary['interface'] = key
            interfaces_list.append(interface_dictionary)

        return convert_list_by_key(interfaces_list, eos_key_maps.INTERFACES_KM, fill_in=True,  whitelist=['interface'])

    @staticmethod
    def _uptime_to_string(uptime):
        days = uptime / (24 * 60 * 60)
        uptime = uptime % (24 * 60 * 60)

        hours = uptime / (60 * 60)
        uptime = uptime % (60 * 60)

        mins = uptime / 60
        uptime = uptime % 60

        seconds = uptime

        return '%02d:%02d:%02d:%02d' % (days, hours, mins, seconds)

    @staticmethod
    def _parse_response(response, raw_text):
        if raw_text:
            return [x['result']['output'] for x in response]
        else:
            return [x['result'] for x in response]

    def backup_running_config(self, filename):
        with open(filename, 'w') as f:
            f.write(self.running_config)

    def checkpoint(self, checkpoint_file):
        self.show('copy running-config %s' % checkpoint_file)

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
            raise CommandListError(commands, e.commands[-1], e.message)

    @property
    def facts(self):
        if self._facts is None:
            sh_version_output = self.show('show version')
            self._facts = convert_dict_by_key(sh_version_output, eos_key_maps.BASIC_FACTS_KM)
            self._facts['uptime'] = int(time.time() - sh_version_output['bootupTimestamp'])
            self._facts['uptime_string'] = self._uptime_to_string(self._facts['uptime'])

            sh_hostname_output = self.show('show hostname')
            self._facts.update(convert_dict_by_key(
                    sh_hostname_output, {}, fill_in=True, whitelist=['hostname', 'fqdn']))

            self._facts['interfaces'] = self._get_interface_list()
            self._facts['vlans'] = self._get_vlan_list()
            self._facts['vendor'] = self.vendor

        return self._facts

    def file_copy(self, src, dest=None, **kwargs):
        fc = EOSFileCopy(self, src, dest)
        fc.send()

    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        fc = EOSFileCopy(self, src, dest)
        if fc.remote_file_exists() and fc.already_transferred():
            return True

        return False

    def get_boot_options(self):
        image = self.show('show boot-config')['softwareImage']
        image = image.replace('flash:', '')

        return dict(sys=image)

    def install_os(self, image_name, **vendor_specifics):
        # TODO: Validate this works
        # TODO: Add validation that OS was installed properly
        self.set_boot_options(image_name)
        self.reboot()

    def open(self):
        pass

    def reboot(self, timer=0):
        if timer != 0:
            raise RebootTimerError(self.device_type)

        self.show('reload now')

    def rollback(self, rollback_to):
        try:
            self.show('configure replace %s force' % rollback_to)
        except (CommandError, CommandListError):
            raise RollbackError('Rollback unsuccessful. %s may not exist.' % rollback_to)

    @property
    def running_config(self):
        if self._running_config is None:
            self._running_config = self.show('show running-config', raw_text=True)

        return self._running_config

    def save(self, filename='startup-config'):
        self.show('copy running-config %s' % filename)

    def set_boot_options(self, image_name, **vendor_specifics):
        self.show('install source %s' % image_name)

    def show(self, command, raw_text=False):
        try:
            response_list = self.show_list([command], raw_text=raw_text)
        except CommandListError as e:
            raise CommandError(e.command, e.message)

        return response_list[0]

    def show_list(self, commands, raw_text=False):
        encoding = 'text' if raw_text else 'json'

        try:
            data = strip_unicode(
                self._parse_response(self.native.enable(commands, encoding=encoding), raw_text=raw_text))
        except EOSCommandError as e:
            raise CommandListError(commands, e.commands[-1], e.message)

        return data

    @property
    def startup_config(self):
        if self._startup_config is None:
            self._startup_config = self.show('show startup-config', raw_text=True)

        return self._startup_config
