from .base_device import BaseDevice
from pynxos.device import Device as NXOSNative

class NXOSDevice(BaseDevice):
    def __init__(self, host, username, password, transport=u'http', timeout=30, **kwargs):
        super(self.__class__, self).__init__(host, username, password)
        self.transport = transport
        self.timeout = timeout

        self.native = NXOSNative(host, username, password, transport=transport, timeout=timeout)

    def open(self):
        pass

    def close(self):
        pass

    def config(self, command):
        return self.native.config(command)

    def config_list(self, commands):
        return self.native.config_list(commands)

    def show(self, command, raw_text=False):
        return self.native.show(command, raw_text=raw_text)

    def show_list(self, commands, raw_text=False):
        return self.native.show_list(commands, raw_text=raw_text)

    def save(self, filename='startup-config'):
        return self.native.save(filename=filename)

    @property
    def facts(self):
        facts = self.native.facts
        facts['vendor'] = 'Cisco'
        return facts

    @property
    def running_config(self):
        return self.native.running_config