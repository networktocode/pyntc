import signal
import os
import re

from .base_device import BaseDevice
from pyntc.errors import CommandError, NTCError
from pyntc.templates import get_template_dir, get_structured_data
from pyntc.data_model.converters import convert_dict_by_key
from pyntc.data_model.key_maps import ios_key_maps

from netmiko import ConnectHandler
from netmiko import FileTransfer


class FileTransferError(NTCError):
    pass

class RebootSignal(NTCError):
    pass

class IOSDevice(BaseDevice):
    def __init__(self, host, username, password, secret='', port=22, **kwargs):
        super(IOSDevice, self).__init__(host, username, password, vendor='Cisco', device_type='ios')

        self.native = None

        self.host = host
        self.username = username
        self.password = password
        self.secret = secret
        self.port = int(port)

    def open(self):
        self.native = ConnectHandler(device_type='cisco_ios',
                                     ip=self.host,
                                     username=self.username,
                                     password=self.password,
                                     port=self.port,
                                     secret=self.secret,
                                     verbose=False)

    def close(self):
        self.native.disconnect()

    def _enter_config(self):
        if not self.native.check_config_mode():
            self.native.config_mode()

    def _enable(self):
        if self.native.check_config_mode():
            self.native.exit_config_mode()

        if not self.native.check_enable_mode():
            self.native.enable()

    def _send_command(self, command):
        response = self.native.send_command(command)
        if response.startswith == '% ':
            raise CommandError(response)

        return response

    def config(self, command):
        self._enter_config()
        self._send_command(command)
        self.native.exit_config_mode()

    def config_list(self, commands):
        self._enter_config()
        for command in commands:
            self._send_command(command)
        self.native.exit_config_mode()

    def show(self, command):
        self._enable()
        return self._send_command(command)

    def show_list(self, commands):
        self._enable()

        responses = []
        for command in commands:
            responses.append(self._send_command(command))

        return responses

    def save(self, filename='startup-config'):
        self.show_list(['copy running-config %s' % filename, '\n', '\n'])
        return True

    def file_copy(self, src, dest=None):
        if dest is None:
            dest = src
        fc = FileTransfer(self.native, src, dest)
        if not fc.verify_space_available():
            raise FileTransferError('Not enough space available.')
        if fc.check_file_exists() and fc.compare_md5():
            return

        fc.enable_scp()
        fc.establish_scp_conn()
        fc.transfer_file()
        fc.close_scp_chan()

    def reboot(self, timer=0, confirm=False):
        if confirm:
            def handler(signum, frame):
                raise RebootSignal('Interupting after reload')

            signal.signal(signal.SIGALRM, handler)
            signal.alarm(10)

            try:
                if timer > 0:
                    first_response = self.show('reload in %d' % timer)
                else:
                    first_response = self.show('reload')

                if 'System configuration' in first_response:
                    self.native.send_command('no')

                self.native.send_command('\n')
            except RebootSignal:
                signal.alarm(0)

            signal.alarm(0)
        else:
            print('Need to confirm reboot with confirm=True')

    def install_os(self, image_name, **vendor_specifics):
        self.config('boot system flash' % image_name)
        self.save()

    def backup_running_config(self, filename):
        with open(filename, 'w') as f:
            f.write(self.running_config)

    def _uptime_components(self, uptime_full_string):
        match_days = re.search(r'(\d+) days?', uptime_full_string)
        match_hours = re.search(r'(\d+) hours?', uptime_full_string)
        match_minutes = re.search(r'(\d+) minutes?', uptime_full_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0

        return days, hours, minutes

    def _uptime_to_string(self, uptime_full_string):
        days, hours, minutes = self._uptime_components(uptime_full_string)
        return '%02d:%02d:%02d:00' % (days, hours, minutes)

    def _uptime_to_seconds(self, uptime_full_string):
        days, hours, minutes = self._uptime_components(uptime_full_string)

        seconds = days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60

        return seconds

    def _interfaces_detailed_list(self):
        ip_int_br_out = self.show('show ip int br')
        ip_int_br_data = get_structured_data('cisco_ios_show_ip_int_brief.template', ip_int_br_out)

        return ip_int_br_data

    def _show_vlan(self):
        show_vlan_out = self.show('show vlan')
        show_vlan_data = get_structured_data('cisco_ios_show_vlan.template', show_vlan_out)

        return show_vlan_data

    def _raw_version_data(self):
        show_version_out = self.show('show version')
        version_data = get_structured_data('cisco_ios_show_version.template', show_version_out)[0]

        return version_data

    def _show_version_facts(self):
        version_data = self._raw_version_data()
        show_version_facts = convert_dict_by_key(version_data, ios_key_maps.BASIC_FACTS_KM)

        return show_version_facts


    @property
    def facts(self):
        '''
        '''
        if hasattr(self, '_facts'):
            return self._facts

        facts = {}
        facts['vendor'] = self.vendor

        version_data = self._raw_version_data()
        show_version_facts = convert_dict_by_key(version_data, ios_key_maps.BASIC_FACTS_KM)

        facts.update(show_version_facts)

        uptime_full_string = version_data['uptime']
        facts['uptime'] = self._uptime_to_seconds(uptime_full_string)
        facts['uptime_string'] = self._uptime_to_string(uptime_full_string)

        facts['fqdn'] = 'N/A'
        facts['interfaces'] = list(x['intf'] for x in self._interfaces_detailed_list())
        facts['vlans'] = list(x['vlan_id'] for x in self._show_vlan())

        # ios-specific facts
        ios_facts = facts['ios'] = {}
        ios_facts['config_register'] = version_data['config_register']

        self._facts = facts
        return facts


    @property
    def running_config(self):
        return self.show('show running-config')

    @property
    def startup_config(self):
        return self.show('show startup-config')
