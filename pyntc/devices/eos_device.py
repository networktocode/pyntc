from .base_device import BaseDevice
from pyntc.errors import CommandError
from pyntc.data_model.converters import convert_dict_by_key, convert_list_by_key
from pyntc.data_model.key_maps import eos_key_maps

from pyeapi import connect as eos_connect
from pyeapi.client import Node as EOSNative
from pyeapi.eapilib import CommandError as EOSCommandError

class EOSDevice(BaseDevice):
    def __init__(self, host, username, password, transport=u'http', timeout=60, **kwargs):
        super(self.__class__, self).__init__(host, username, password, vendor='Arista', device_type='eos')
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
        command = str(command)
        response_list = self.config_list([command])
        return response_list[0]

    def config_list(self, commands):
        try:
            return list(None for x in self.native.config(commands) if x == {})
        except EOSCommandError as e:
            raise CommandError(e.message)

    def show(self, command, raw_text=False):
        command = str(command)
        response_list = self.show_list([command], raw_text=raw_text)
        return response_list[0]

    def show_list(self, commands, raw_text=False):
        if raw_text:
            encoding = 'text'
        else:
            encoding = 'json'

        try:
            return self._parse_response(self.native.enable(commands, encoding=encoding), raw_text=raw_text)
        except EOSCommandError as e:
            raise CommandError(e.message)

    def save(self, filename='startup-config'):
        return self.show('copy running-config %s' % filename)

    def _interfaces_status_list(self):
        interfaces_list = []
        interfaces_status_dictionary = self.show('show interfaces status')['interfaceStatuses']
        for key in interfaces_status_dictionary:
            interface_dictionary = interfaces_status_dictionary[key]
            interface_dictionary['interface'] = key
            interfaces_list.append(interface_dictionary)

        return interfaces_list

    @property
    def facts(self):
        facts = {}
        facts['vendor'] = self.vendor

        sh_version_output = self.show('show version')
        facts.update(convert_dict_by_key(sh_version_output, eos_key_maps.BASIC_FACTS_KM))

        interfaces_status_list = self._interfaces_status_list()
        facts['interfaces'] = convert_list_by_key(interfaces_status_list, eos_key_maps.INTERFACES_KM, fill_in=True, whitelist=['interface'])

        return facts

    @property
    def running_config(self):
        return self.show('show running-config', raw_text=True)['output']