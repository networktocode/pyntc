import os
import re
import time
import hashlib
from tempfile import NamedTemporaryFile

from jnpr.junos import Device as JunosNativeDevice
from jnpr.junos.utils.config import Config as JunosNativeConfig
from jnpr.junos.utils.fs import FS as JunosNativeFS
from jnpr.junos.utils.sw import SW as JunosNativeSW
from jnpr.junos.utils.scp import SCP
from jnpr.junos.op.ethport import EthPortTable
from jnpr.junos.exception import ConfigLoadError

from .tables.jnpr.loopback import LoopbackTable
from .base_device import BaseDevice, fix_docs

from pyntc.errors import CommandError, CommandListError, FileTransferError, RebootTimeoutError


@fix_docs
class JunosDevice(BaseDevice):
    """Juniper JunOS Device Implementation."""

    vendor = "juniper"

    def __init__(self, host, username, password, *args, **kwargs):
        super().__init__(host, username, password, *args, device_type="juniper_junos_netconf", **kwargs)

        self.native = JunosNativeDevice(*args, host=host, user=username, passwd=password, **kwargs)
        self.open()
        self.cu = JunosNativeConfig(self.native)
        self.fs = JunosNativeFS(self.native)
        self.sw = JunosNativeSW(self.native)

    def _file_copy_local_file_exists(self, filepath):
        return os.path.isfile(filepath)

    def _file_copy_local_md5(self, filepath, blocksize=2 ** 20):
        if self._file_copy_local_file_exists(filepath):
            m = hashlib.md5()  # nosec
            with open(filepath, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    def _file_copy_remote_md5(self, filename):
        return self.fs.checksum(filename)

    def _get_interfaces(self):
        eth_ifaces = EthPortTable(self.native)
        eth_ifaces.get()

        loop_ifaces = LoopbackTable(self.native)
        loop_ifaces.get()

        ifaces = eth_ifaces.keys()
        ifaces.extend(loop_ifaces.keys())

        return ifaces

    def _image_booted(self, image_name, **vendor_specifics):
        raise NotImplementedError

    def _uptime_components(self, uptime_full_string):
        match_days = re.search(r"(\d+) days?", uptime_full_string)
        match_hours = re.search(r"(\d+) hours?", uptime_full_string)
        match_minutes = re.search(r"(\d+) minutes?", uptime_full_string)
        match_seconds = re.search(r"(\d+) seconds?", uptime_full_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0
        seconds = int(match_seconds.group(1)) if match_seconds else 0

        return days, hours, minutes, seconds

    def _uptime_to_seconds(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)

        seconds += days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60

        return seconds

    def _uptime_to_string(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)
        return "%02d:%02d:%02d:%02d" % (days, hours, minutes, seconds)

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                return
            except:  # noqa E722 # nosec
                pass

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        with open(filename, "w") as f:
            f.write(self.running_config)

    @property
    def boot_options(self):
        return self.os_version

    def checkpoint(self, filename):
        self.save(filename)

    def close(self):
        if self.connected:
            self.native.close()

    def config(self, command, format="set"):
        try:
            self.cu.load(command, format=format)
            self.cu.commit()
        except ConfigLoadError as e:
            raise CommandError(command, e.message)

    def config_list(self, commands, format="set"):
        try:
            for command in commands:
                self.cu.load(command, format=format)

            self.cu.commit()
        except ConfigLoadError as e:
            raise CommandListError(commands, command, e.message)

    @property
    def connected(self):
        return self.native.connected

    @property
    def uptime(self):
        try:
            native_uptime_string = self.native.facts["RE0"]["up_time"]
        except (AttributeError, TypeError):
            native_uptime_string = None

        if self._uptime is None:
            if native_uptime_string is not None:
                self._uptime = self._uptime_to_seconds(native_uptime_string)

        return self._uptime

    @property
    def uptime_string(self):
        try:
            native_uptime_string = self.native.facts["RE0"]["up_time"]
        except (AttributeError, TypeError):
            native_uptime_string = None

        if self._uptime_string is None:
            self._uptime_string = self._uptime_to_string(native_uptime_string)

        return self._uptime_string

    @property
    def hostname(self):
        if self._hostname is None:
            self._hostname = self.native.facts.get("hostname")

        return self._hostname

    @property
    def interfaces(self):
        if self._interfaces is None:
            self._interfaces = self._get_interfaces()

        return self._interfaces

    @property
    def fqdn(self):
        if self._fqdn is None:
            self._fqdn = self.native.facts.get("fqdn")

        return self._fqdn

    @property
    def model(self):
        if self._model is None:
            self._model = self.native.facts.get("model")

        return self._model

    @property
    def os_version(self):
        if self._os_version is None:
            self._os_version = self.native.facts.get("version")

        return self._os_version

    @property
    def serial_number(self):
        if self._serial_number is None:
            self._serial_number = self.native.facts.get("serialnumber")

        return self._serial_number

    def file_copy(self, src, dest=None, **kwargs):
        if not self.file_copy_remote_exists(src, dest, **kwargs):
            if dest is None:
                dest = os.path.basename(src)

            with SCP(self.native) as scp:
                scp.put(src, remote_path=dest)

            if not self.file_copy_remote_exists(src, dest, **kwargs):
                raise FileTransferError(
                    message="Attempted file copy, but could not validate file existed after transfer"
                )

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        if dest is None:
            dest = os.path.basename(src)

        local_hash = self._file_copy_local_md5(src)
        remote_hash = self._file_copy_remote_md5(dest)
        if local_hash is not None and local_hash == remote_hash:
            return True
        return False

    def install_os(self, image_name, **vendor_specifics):
        raise NotImplementedError

    def open(self):
        if not self.connected:
            self.native.open()

    def reboot(self, timer=0, confirm=False):
        self.sw = JunosNativeSW(self.native)
        if confirm:
            self.sw.reboot(in_min=timer)
        else:
            print("Need to confirm reboot with confirm=True")

    def rollback(self, filename):
        self.native.timeout = 60

        temp_file = NamedTemporaryFile()

        with SCP(self.native) as scp:
            scp.get(filename, local_path=temp_file.name)

        self.cu.load(path=temp_file.name, format="text", overwrite=True)
        self.cu.commit()

        temp_file.close()

        self.native.timeout = 30

    @property
    def running_config(self):
        return self.show("show config")

    def save(self, filename=None):
        if filename is None:
            self.cu.commit()
            return

        temp_file = NamedTemporaryFile()
        temp_file.write(self.show("show config"))
        temp_file.flush()

        with SCP(self.native) as scp:
            scp.put(temp_file.name, remote_path=filename)

        temp_file.close()
        return True

    def set_boot_options(self, sys):
        raise NotImplementedError

    def show(self, command, raw_text=True):
        if not raw_text:
            raise ValueError(
                'Juniper only supports raw text output. \
                Append " | display xml" to your commands for a structured string.'
            )

        if not command.startswith("show"):
            raise CommandError(command, 'Juniper "show" commands must begin with "show".')

        return self.native.cli(command, warning=False)

    def show_list(self, commands, raw_text=True):
        responses = []
        for command in commands:
            responses.append(self.show(command, raw_text=raw_text))

        return responses

    @property
    def startup_config(self):
        return self.show("show config")
