from .base_device import BaseDevice
from pyntc.errors import CommandError
from pyntc.data_model.converters import strip_unicode

from pynxos.device import Device as NXOSNative
from pynxos.errors import CLIError

class NXOSDevice(BaseDevice):
    def __init__(self, host, username, password, transport='http', timeout=30, **kwargs):
        super(NXOSDevice, self).__init__(host, username, password, vendor='Cisco', device_type='nxos')
        self.transport = transport
        self.timeout = timeout

        self.native = NXOSNative(host, username, password, transport=transport, timeout=timeout)

    def open(self):
        pass

    def close(self):
        pass

    def config(self, command):
        try:
            self.native.config(command)
        except CLIError as e:
            raise CommandError(str(e))

    def config_list(self, commands):
        try:
            self.native.config_list(commands)
        except CLIError as e:
            raise CommandError(str(e))

    def show(self, command, raw_text=False):
        try:
            return strip_unicode(self.native.show(command, raw_text=raw_text))
        except CLIError as e:
            raise CommandError(str(e))

    def show_list(self, commands, raw_text=False):
        try:
            return strip_unicode(self.native.show_list(commands, raw_text=raw_text))
        except CLIError as e:
            raise CommandError(str(e))

    def save(self, filename='startup-config'):
        return self.native.save(filename=filename)

    @property
    def facts(self):
        facts = self.native.facts
        facts['vendor'] = self.vendor
        return facts

    @property
    def running_config(self):
        return self.native.running_config

    @property
    def startup_config(self):
        return self.show('show startup-config', raw_text=True)