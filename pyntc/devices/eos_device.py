from .base_device import BaseDevice
from pyeapi import connect as eos_connect
from pyeapi.client import Node as EOSNative

class EOSDevice(BaseDevice):
    def __init__(self, host, username, password, transport=u'http', timeout=60, **kwargs):
        super(self.__class__, self).__init__(host, username, password)
        self.transport = transport
        self.timeout = timeout

        self.connection = eos_connect(
            transport, host=host, username=username, password=password, timeout=timeout)

        self.native = EOSNative(self.connection)

    def open(self):
        pass

    def close(self):
        pass

    def config(self, command):
        command = str(command)
        return self.native.config(command)[0]

    def config_list(self, commands):
        return self.native.config(commands)

    def show(self, command):
        return self.native.enable(command)[0]

    def show_list(self, commands):
        return self.native.enable(commands)

    def save(self):
        pass

    @property
    def facts(self):
        pass

    @property
    def running_config(self):
        pass