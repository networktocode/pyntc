from .base_device import BaseDevice
from pyntc.errors import CommandError

from pynxos.device import Device as NXOSNative
from pynxos.errors import CLIError

class NXOSDevice(BaseDevice):
    def __init__(self, vendor, device_type, host, username, password, transport=u'http', timeout=30, **kwargs):
        super(self.__class__, self).__init__(vendor, device_type, host, username, password)
        self.transport = transport
        self.timeout = timeout

        self.native = NXOSNative(host, username, password, transport=transport, timeout=timeout)

    def open(self):
        pass

    def close(self):
        pass

    def config(self, command):
        try:
            return self.native.config(command)
        except CLIError as e:
            raise CommandError(e.message)

    def config_list(self, commands):
        try:
            return self.native.config_list(commands)
        except CLIError as e:
            raise CommandError(e.message)

    def show(self, command, raw_text=False):
        try:
            return self.native.show(command, raw_text=raw_text)
        except CLIError as e:
            raise CommandError(e.message)

    def show_list(self, commands, raw_text=False):
        try:
            return self.native.show_list(commands, raw_text=raw_text)
        except CLIError as e:
            raise CommandError(e.message)

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