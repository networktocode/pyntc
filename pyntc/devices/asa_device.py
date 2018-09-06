"""Module for using a Cisco ASA device over SSH.
"""

import re

from netmiko import ConnectHandler

from pyntc.errors import NTCError
from pyntc.templates import get_structured_data
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

    def set_boot_options(self, image_name, **vendor_specifics):
        current_boot = self.show("show running-config | inc ^boot system ")

        if current_boot:
            current_images = current_boot.splitlines()
        else:
            current_images = []

        commands_to_exec = ["no {}".format(image) for image in current_images]
        commands_to_exec.append("boot system {}{}".format(
            vendor_specifics.get('image_location', ''), image_name))

        self.config_list(commands_to_exec)

    def get_boot_options(self):
        show_boot_out = self.show('show boot | i BOOT variable')
        # Improve regex to get only the first boot $var in the sequence!
        boot_path_regex = r'Current BOOT variable = (\S+):\/(\S+)'

        match = re.search(boot_path_regex, show_boot_out)
        if match:
            boot_image = match.group(2)
        else:
            boot_image = None

        return dict(sys=boot_image)

    def _interfaces_detailed_list(self):
        ip_int = self.show('show interface')
        ip_int_data = get_structured_data('cisco_asa_show_interface.template',
                                          ip_int)

        return ip_int_data

    def _raw_version_data(self):
        show_version_out = self.show('show version')
        try:
            version_data = \
                get_structured_data('cisco_asa_show_version.template',
                                    show_version_out)[0]
            return version_data
        except IndexError:
            return {}

    @property
    def facts(self):
        """Implement this once facts' re-factor is done. """
        return {}

    def rollback(self, rollback_to):
        raise NotImplementedError
