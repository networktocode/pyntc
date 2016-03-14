import os
import re
import hashlib
from tempfile import NamedTemporaryFile

from jnpr.junos import Device as JunosNativeDevice
from jnpr.junos.utils.config import Config as JunosNativeConfig
from jnpr.junos.utils.fs import FS as JunosNativeFS
from jnpr.junos.utils.sw import SW as JunosNativdSW
from jnpr.junos.utils.scp import SCP
from jnpr.junos.op.ethport import EthPortTable
from jnpr.junos.exception import ConfigLoadError

from .tables.jnpr.loopback import LoopbackTable
from .base_device import BaseDevice, fix_docs

from pyntc.errors import CommandError, CommandListError

JNPR_DEVICE_TYPE = 'juniper_junos_netconf'

@fix_docs
class JunosDevice(BaseDevice):

    def __init__(self, host, username, password, *args, **kwargs):
        super(JunosDevice, self).__init__(host,
                                          username,
                                          password,
                                          *args,
                                          vendor='juniper',
                                          device_type=JNPR_DEVICE_TYPE,
                                          **kwargs)

        self.native = JunosNativeDevice(*args, host=host, user=username, passwd=password, **kwargs)
        self.open()

        self.cu = JunosNativeConfig(self.native)
        self.fs = JunosNativeFS(self.native)
        self.sw = JunosNativdSW(self.native)

    @property
    def connected(self):
        return self.native.connected

    def open(self):
        if not self.connected:
            self.native.open()

    def close(self):
        if self.connected:
            self.native.close()

    def show(self, command, raw_text=True):
        if not raw_text:
            raise ValueError('Juniper only supports raw text output. \
                Append " | display xml" to your commands for a structured string.')

        if not command.startswith('show'):
            raise CommandError(command, 'Juniper "show" commands must begin with "show".')


        return self.native.cli(command, warning=False)


    def show_list(self, commands, raw_text=True):
        responses = []
        for command in commands:
            responses.append(self.show(command, raw_text=raw_text))

        return responses

    def backup_running_config(self, filename):
        with open(filename, 'w') as f:
            f.write(self.running_config)

    def config(self, command, format='set'):
        try:
            self.cu.load(command, format=format)
            self.cu.commit()
        except ConfigLoadError as e:
            raise CommandError(command, e.message)

    def config_list(self, commands, format='set'):
        try:
            for command in commands:
                self.cu.load(command, format=format)

            self.cu.commit()
        except ConfigLoadError as e:
            raise CommandListError(commands, command, e.message)


    def _uptime_components(self, uptime_full_string):
        match_days = re.search(r'(\d+) days?', uptime_full_string)
        match_hours = re.search(r'(\d+) hours?', uptime_full_string)
        match_minutes = re.search(r'(\d+) minutes?', uptime_full_string)
        match_seconds = re.search(r'(\d+) seconds?', uptime_full_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0
        seconds = int(match_seconds.group(1)) if match_seconds else 0

        return days, hours, minutes, seconds

    def _uptime_to_string(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)
        return '%02d:%02d:%02d:%02d' % (days, hours, minutes, seconds)

    def _uptime_to_seconds(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)

        seconds += days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60

        return seconds

    def _get_interfaces(self):
        eth_ifaces = EthPortTable(self.native)
        eth_ifaces.get()

        loop_ifaces = LoopbackTable(self.native)
        loop_ifaces.get()

        ifaces = eth_ifaces.keys()
        ifaces.extend(loop_ifaces.keys())

        return ifaces

    def checkpoint(self, filename):
        self.save(filename)

    def rollback(self, filename):
        self.native.timeout = 60

        temp_file = NamedTemporaryFile()

        with SCP(self.native) as scp:
            scp.get(filename, local_path=temp_file.name)

        self.cu.load(path=temp_file.name, format='text', overwrite=True)
        self.cu.commit()

        temp_file.close()

        self.native.timeout = 30

    @property
    def facts(self):
        if hasattr(self, '_facts'):
            return self._facts

        native_facts = self.native.facts

        facts = {}
        facts['hostname'] = native_facts['hostname']
        facts['fqdn'] = native_facts['fqdn']
        facts['model'] = native_facts['model']

        native_uptime_string = native_facts['RE0']['up_time']
        facts['uptime'] = self._uptime_to_seconds(native_uptime_string)
        facts['uptime_string'] = self._uptime_to_string(native_uptime_string)

        facts['serial_number'] = native_facts['serialnumber']

        facts['interfaces'] = self._get_interfaces()

        for fact_key in native_facts:
            if fact_key.startswith('version') and fact_key != 'version_info':
                facts['os_version'] = native_facts[fact_key]
                break

        facts['vendor'] = self.vendor
        self._facts = facts
        return self._facts

    def _file_copy_local_file_exists(self, filepath):
        return os.path.isfile(filepath)

    def _file_copy_local_md5(self, filepath, blocksize=2**20):
        if self._file_copy_local_file_exists(filepath):
            m = hashlib.md5()
            with open(filepath, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    def _file_copy_remote_md5(self, filename):
        return self.fs.checksum(filename)

    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        if dest is None:
            dest = os.path.basename(src)

        local_hash = self._file_copy_local_md5(src)
        remote_hash = self._file_copy_remote_md5(dest)
        if local_hash is not None:
            if local_hash == remote_hash:
                return True

        return False

    def file_copy(self, src, dest=None, **kwargs):
        if dest is None:
            dest = os.path.basename(src)

        with SCP(self.native) as scp:
            scp.put(src, remote_path=dest)

    def get_boot_options(self):
        return self.facts['os_version']

    def set_boot_options(self, sys):
        raise NotImplementedError

    def reboot(self, timer=0, confirm=False):
        if confirm:
            self.sw.reboot(in_min=timer)
        else:
            print('Need to confirm reboot with confirm=True')

    @property
    def running_config(self):
        return self.show('show config')

    def save(self, filename=None):
        if filename is None:
            self.cu.commit()
            return

        temp_file = NamedTemporaryFile()
        temp_file.write(self.show('show config'))
        temp_file.flush()

        with SCP(self.native) as scp:
            scp.put(temp_file.name, remote_path=filename)

        temp_file.close()
        return True

    @property
    def startup_config(self):
        return self.show('show config')
