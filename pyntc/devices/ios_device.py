"""Module for using a Cisco IOS device over SSH.
"""

import signal
import os
import re
import time

from pyntc.errors import CommandError, CommandListError, NTCError
from pyntc.templates import get_structured_data
from pyntc.data_model.converters import convert_dict_by_key
from pyntc.data_model.key_maps import ios_key_maps
from .system_features.file_copy.base_file_copy import FileTransferError
from .base_device import BaseDevice, RollbackError, fix_docs


from netmiko import ConnectHandler
from netmiko import FileTransfer


# TODO: Understand purpose and make class do something
class RebootSignal(NTCError):
    pass


@fix_docs
class IOSDevice(BaseDevice):
    def __init__(self, host, username, password, secret='', port=22, **kwargs):
        super(IOSDevice, self).__init__(host, username, password, vendor='cisco', device_type='cisco_ios_ssh')
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

    def _enable(self):
        self.native.exit_config_mode()
        if not self.native.check_enable_mode():
            self.native.enable()

    def _enter_config(self):
        self._enable()
        self.native.config_mode()

    def _file_copy_instance(self, src, dest=None, file_system='flash:'):
        if dest is None:
            dest = os.path.basename(src)

        fc = FileTransfer(self.native, src, dest, file_system=file_system)

        return fc

    def _get_file_system(self):
        self._enable()
        raw_data = self._send_command('dir')
        file_system = re.search(r'flash:|bootflash:', raw_data).group(0)
        return file_system

    def _interfaces_detailed_list(self):
        ip_int_br_out = self.show('show ip int br')
        ip_int_br_data = get_structured_data('cisco_ios_show_ip_int_brief.template', ip_int_br_out)

        return ip_int_br_data

    def _is_already_upgraded(self, request_image):
        show_version = self.show('show version')
        if re.search(request_image.strip(), show_version):
            return True
        return False

    def _is_catalyst(self):
        return self.facts['model'].startswith('WS-')

    def _is_file_in_dir(self, request_image):
        show_file_in_dir = self.show('dir')
        if re.search(request_image, show_file_in_dir):
            return True
        return False

    def _raw_version_data(self):
        show_version_out = self.show('show version')
        try:
            version_data = get_structured_data('cisco_ios_show_version.template', show_version_out)[0]
            return version_data
        except IndexError:
            return {}

    def _reconnect(self, timeout=60):
        counter = 0
        timeout = timeout*4
        while counter < timeout:
            try:
                self.open()
                return True
            except:
                counter += 1
                time.sleep(15)
        raise ValueError('reconnect timeout: could not verified device upgrade')

    def _send_command(self, command, expect=False, expect_string=''):
        if expect:
            if expect_string:
                response = self.native.send_command_expect(command, expect_string=expect_string)
            else:
                response = self.native.send_command_expect(command)
        else:
            response = self.native.send_command_timing(command)

        if '% ' in response or 'Error:' in response:
            raise CommandError(command, response)

        return response

    def _show_vlan(self):
        show_vlan_out = self.show('show vlan')
        show_vlan_data = get_structured_data('cisco_ios_show_vlan.template', show_vlan_out)

        return show_vlan_data

    @staticmethod
    def _uptime_components(uptime_full_string):
        match_days = re.search(r'(\d+) days?', uptime_full_string)
        match_hours = re.search(r'(\d+) hours?', uptime_full_string)
        match_minutes = re.search(r'(\d+) minutes?', uptime_full_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0

        return days, hours, minutes

    def _uptime_to_seconds(self, uptime_full_string):
        days, hours, minutes = self._uptime_components(uptime_full_string)

        seconds = days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60

        return seconds

    def _uptime_to_string(self, uptime_full_string):
        days, hours, minutes = self._uptime_components(uptime_full_string)
        return '%02d:%02d:%02d:00' % (days, hours, minutes)

    def backup_running_config(self, filename):
        with open(filename, 'w') as f:
            f.write(self.running_config)

    def change_config_register(self, register='0x2102'):
        if self.facts['cisco_ios_ssh']['config_register'] == register:
            return False
        else:
            try:
                self.config('config-register {}'.format(register))
                return True
            except :
                return False

    def checkpoint(self, checkpoint_file):
        self.save(filename=checkpoint_file)

    def close(self):
        if self._connected:
            self.native.disconnect()
            self._connected = False

    def config(self, command):
        self._enter_config()
        self._send_command(command)
        self.native.exit_config_mode()

    def config_list(self, commands):
        self._enter_config()
        entered_commands = []
        for command in commands:
            entered_commands.append(command)
            try:
                self._send_command(command)
            except CommandError as e:
                raise CommandListError(entered_commands, command, e.cli_error_msg)
        self.native.exit_config_mode()

    @property
    def facts(self):
        if self._facts is None:
            version_data = self._raw_version_data()
            self._facts = convert_dict_by_key(version_data, ios_key_maps.BASIC_FACTS_KM)
            self._facts['uptime'] = self._uptime_to_seconds(version_data['uptime'])
            self._facts['uptime_string'] = self._uptime_to_string(version_data['uptime'])
            self._facts['interfaces'] = [x['intf'] for x in self._interfaces_detailed_list()]
            if self._facts['model'].startswith('WS'):
                self._facts['vlans'] = [str(x['vlan_id']) for x in self._show_vlan()]
            else:
                self._facts['vlans'] = []

            self._facts['fqdn'] = 'N/A'
            self._facts['vendor'] = self.vendor

            # ios-specific facts
            self._facts['cisco_ios_ssh'] = {'config_register': version_data['config_register']}

        return self._facts

    def file_copy(self, src, dest=None, file_system='flash:'):
            fc = self._file_copy_instance(src, dest, file_system=file_system)
            self._enable()
            if not fc.verify_space_available():
                raise FileTransferError('Not enough space available.')
            try:
                fc.enable_scp()
                fc.establish_scp_conn()
                fc.transfer_file()
            # TODO: Discover expected exceptions and raise appropriately
            except:
                raise FileTransferError
            finally:
                fc.close_scp_chan()

    def file_copy_remote_exists(self, src, dest=None):
        file_system = self._get_file_system()
        fc = self._file_copy_instance(src, dest, file_system=file_system)
        self._enable()
        if fc.check_file_exists() and fc.compare_md5():
            return True

        return False

    def get_boot_options(self):
        # TODO: CREATE A MOCK FOR TESTING THIS FUCTION
        if self._is_catalyst():
            show_boot_out = self.show('show boot')
            boot_path_regex = r'(BOOT variable\s+=\s+|BOOT path-list\s+:\s+)(\S+?)(?:;|)\s'
            match = re.search(boot_path_regex, show_boot_out)
            if match:
                boot_path = match.group(2)
                boot_image = boot_path.replace('flash:/', '')
            else:
                boot_image = None

        else:
            show_boot_out = self.show('show run | inc boot')
            boot_path_regex = r'boot system flash (\S+)'

            match = re.search(boot_path_regex, show_boot_out)
            if match:
                boot_image = match.group(1)
            else:
                boot_image = None

        return dict(sys=boot_image)

    def install_os(self, image_name, **vendor_specifics):
        # TODO:
        if self._is_already_upgraded(image_name):
            return False

        if not self._is_file_in_dir(image_name):
            raise ValueError('Image is not on device')

        current_boot_option = self.get_boot_options().get('sys')
        self.set_boot_options(image_name)
        self.save()
        new_boot_option = self.get_boot_options().get('sys')
        self.reboot()
        reconnected = self._reconnect()
        if reconnected:
            if self._is_already_upgraded(image_name):
                return True

    def open(self):
        if self._connected:
            try:
                self.native.find_prompt()
            # TODO: Discover expected exceptions and raise appropriately
            except:
                self._connected = False

        if not self._connected:
            self.native = ConnectHandler(device_type='cisco_ios',
                                         ip=self.host,
                                         username=self.username,
                                         password=self.password,
                                         port=self.port,
                                         global_delay_factor=self.global_delay_factor,
                                         secret=self.secret,
                                         verbose=False)
            self._connected = True

    def reboot(self, timer=0):
        def handler():
            raise RebootSignal('Interrupting after reload')

        signal.signal(signal.SIGALRM, handler)
        signal.alarm(10)

        try:
            if timer > 0:
                first_response = self.show('reload in %d' % timer)
            else:
                first_response = self.show('reload')

            if 'System configuration' in first_response:
                self.native.send_command_timing('no')

            self.native.send_command_timing('\n')
        except RebootSignal:
            signal.alarm(0)
            time.sleep(30)

        signal.alarm(0)


    def rollback(self, rollback_to):
        try:
            self.show('configure replace flash:%s force' % rollback_to)
        except CommandError:
            raise RollbackError('Rollback unsuccessful. %s may not exist.' % rollback_to)

    @property
    def running_config(self):
        if self._running_config is None:
            self._running_config = self.show('show running-config', expect=True)

        return self._running_config

    def save(self, filename='startup-config'):
        command = 'copy running-config %s' % filename
        # Changed to send_command_timing to not require a direct prompt return.
        self.native.send_command_timing(command)
        # If the user has enabled 'file prompt quiet' which dose not require any confirmation or feedback.
        # This will send return without requiring an OK.
        # Send a return to pass the [OK]? message - Incease delay_factor for looking for response.
        self.native.send_command_timing('\n', delay_factor=2)
        # Confirm that we have a valid prompt again before returning.
        self.native.find_prompt()

    def set_boot_options(self, image_name, **vendor_specifics):
        file_system = self._get_file_system()
        if self._is_catalyst():
            self.config_list(['no boot system', 'boot system {}/%s'.format(file_system) % image_name])
        else:
            self.config_list(['no boot system', 'boot system {} %s'.format(file_system.replace(':','')) % image_name])

    def show(self, command, expect=False, expect_string=''):
        self._enable()
        return self._send_command(command, expect=expect, expect_string=expect_string)

    def show_list(self, commands, raw_text=False):
        self._enable()

        responses = []
        entered_commands = []
        for command in commands:
            entered_commands.append(command)
            try:
                responses.append(self._send_command(command))
            except CommandError as e:
                raise CommandListError(entered_commands, command, e.cli_error_msg)

        return responses

    @property
    def startup_config(self):
        if self._startup_config is None:
            self._startup_config = self.show('show startup-config')

        return self._startup_config
