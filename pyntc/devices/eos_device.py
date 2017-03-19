"""Module for using an Arista EOS device over the eAPI.
"""

import time

from pyntc.errors import CommandError, CommandListError, NTCError
from pyntc.data_model.converters import convert_dict_by_key, \
    convert_list_by_key, strip_unicode
from pyntc.data_model.key_maps import eos_key_maps
from .system_features.file_copy.eos_file_copy import EOSFileCopy
from .system_features.vlans.eos_vlans import EOSVlans
from .base_device import BaseDevice, RollbackError, RebootTimerError, fix_docs

from pyeapi import connect as eos_connect
from pyeapi.client import Node as EOSNative
from pyeapi.eapilib import CommandError as EOSCommandError

EOS_API_DEVICE_TYPE = 'arista_eos_eapi'


class RebootSignal(NTCError):
    pass


@fix_docs
class EOSDevice(BaseDevice):

    def __init__(self, host, username, password, transport='http', timeout=60, **kwargs):
        super(EOSDevice, self).__init__(host, username, password, vendor='arista', device_type=EOS_API_DEVICE_TYPE)
        self.transport = transport
        self.timeout = timeout

        self.connection = eos_connect(
            transport, host=host, username=username, password=password, timeout=timeout)

        self.native = EOSNative(self.connection)

    def open(self):
        pass

    def close(self):
        pass

    def _parse_response(self, response, raw_text):
        if raw_text:
            return list(x['result']['output'] for x in response)
        else:
            return list(x['result'] for x in response)

    def config(self, command):
        try:
            self.config_list([command])
        except CommandListError as e:
            raise CommandError(e.command, e.message)

    def config_list(self, commands):
        try:
            self.native.config(commands)
        except EOSCommandError as e:
            raise CommandListError(
                commands, e.commands[len(e.commands) - 1], e.message)

    def show(self, command, raw_text=False):
        try:
            response_list = self.show_list([command], raw_text=raw_text)
            return response_list[0]
        except CommandListError as e:
            raise CommandError(e.command, e.message)

    def show_list(self, commands, raw_text=False):
        if raw_text:
            encoding = 'text'
        else:
            encoding = 'json'

        try:
            return strip_unicode(
                self._parse_response(
                    self.native.enable(
                        commands, encoding=encoding), raw_text=raw_text))
        except EOSCommandError as e:
            raise CommandListError(commands,
                                   e.commands[len(e.commands) - 1],
                                   e.message)

    def save(self, filename='startup-config'):
        self.show('copy running-config %s' % filename)
        return True

    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        fc = EOSFileCopy(self, src, dest)
        if fc.remote_file_exists():
            if fc.already_transfered():
                return True
        return False

    def file_copy(self, src, dest=None, **kwargs):
        fc = EOSFileCopy(self, src, dest)
        fc.send()

    def reboot(self, confirm=False, timer=0):
        if timer != 0:
            raise RebootTimerError(self.device_type)

        if confirm:
            self.show('reload now')
        else:
            print('Need to confirm reboot with confirm=True')

    def get_boot_options(self):
        image = self.show('show boot-config')['softwareImage']
        image = image.replace('flash:', '')
        return dict(sys=image)

    def set_boot_options(self, image_name, **vendor_specifics):
        self.show('install source %s' % image_name)

    def backup_running_config(self, filename):
        with open(filename, 'w') as f:
            f.write(self.running_config)

    def _interfaces_status_list(self):
        interfaces_list = []
        interfaces_status_dictionary = self.show(
            'show interfaces status')['interfaceStatuses']
        for key in interfaces_status_dictionary:
            interface_dictionary = interfaces_status_dictionary[key]
            interface_dictionary['interface'] = key
            interfaces_list.append(interface_dictionary)

        return convert_list_by_key(interfaces_list,
                                   eos_key_maps.INTERFACES_KM,
                                   fill_in=True,
                                   whitelist=['interface'])

    def _get_interface_list(self):
        iface_detailed_list = self._interfaces_status_list()
        iface_list = sorted(list(x['interface'] for x in iface_detailed_list))

        return iface_list

    def _get_vlan_list(self):
        vlans = EOSVlans(self)
        vlan_list = vlans.get_list()

        return vlan_list

    def _uptime_to_string(self, uptime):
        days = uptime / (24 * 60 * 60)
        uptime = uptime % (24 * 60 * 60)

        hours = uptime / (60 * 60)
        uptime = uptime % (60 * 60)

        mins = uptime / 60
        uptime = uptime % 60

        seconds = uptime

        return '%02d:%02d:%02d:%02d' % (days, hours, mins, seconds)

    def rollback(self, rollback_to):
        try:
            self.show('configure replace %s force' % rollback_to)
        except (CommandError, CommandListError):
            raise RollbackError(
                'Rollback unsuccessful. %s may not exist.' % rollback_to)

    def checkpoint(self, checkpoint_file):
        self.show('copy running-config %s' % checkpoint_file)

    @property
    def facts(self):
        if hasattr(self, '_facts'):
            return self._facts

        facts = {}
        facts['vendor'] = self.vendor

        sh_version_output = self.show('show version')
        facts.update(
            convert_dict_by_key(
                sh_version_output, eos_key_maps.BASIC_FACTS_KM))

        uptime = int(time.time() - sh_version_output['bootupTimestamp'])
        facts['uptime'] = uptime
        facts['uptime_string'] = self._uptime_to_string(uptime)

        sh_hostname_output = self.show('show hostname')
        facts.update(
            convert_dict_by_key(
                sh_hostname_output, {}, fill_in=True, whitelist=['hostname', 'fqdn']))

        facts['interfaces'] = self._get_interface_list()
        facts['vlans'] = self._get_vlan_list()

        self._facts = facts
        return facts

    @property
    def running_config(self):
        return self.show('show running-config', raw_text=True)

    @property
    def startup_config(self):
        return self.show('show startup-config', raw_text=True)
