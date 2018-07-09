"""Module for using a Cisco ASA device over SSH.
"""

from netmiko import ConnectHandler

from pyntc.errors import NTCError
from .base_device import fix_docs
from .ios_device import IOSDevice

ASA_SSH_DEVICE_TYPE = 'cisco_asa_ssh'


class RebootSignal(NTCError):
    pass


@fix_docs
class ASADevice(IOSDevice):
    def __init__(self, host, username, password, secret='', port=22, **kwargs):
        super(IOSDevice, self).__init__(host, username, password,
                                        vendor='cisco',
                                        device_type=ASA_SSH_DEVICE_TYPE)

        self.native = None

        self.host = host
        self.username = username
        self.password = password
        self.secret = secret
        self.port = int(port)
        self.global_delay_factor = kwargs.get('global_delay_factor', 1)
        self.delay_factor = kwargs.get('delay_factor', 1)
        self._connected = False
        self.open()

    def open(self):
        if self._connected:
            try:
                self.native.find_prompt()
            except:
                self._connected = False

        if not self._connected:
            self.native = ConnectHandler(device_type='cisco_asa',
                                         ip=self.host,
                                         username=self.username,
                                         password=self.password,
                                         port=self.port,
                                         global_delay_factor=self.global_delay_factor,
                                         secret=self.secret,
                                         verbose=False)
            self._connected = True
