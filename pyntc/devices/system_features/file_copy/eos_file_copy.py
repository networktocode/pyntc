import paramiko
import os
import hashlib
import re
from scp import SCPClient
from .base_file_copy import BaseFileCopy, FileTransferError

class EOSFileCopy(BaseFileCopy):
    def __init__(self, device, local, remote=None, port=22):
        self.device = device
        self.local = local
        self.remote = remote or os.path.basename(local)
        self.port = port

    def get_remote_size(self):
        dir_out = self.device.show('dir', raw_text=True)
        match = re.search(r'(\d+) bytes free', dir_out)
        bytes_free = match.group(1)

        return int(bytes_free)

    def enough_remote_space(self):
        remote_size = self.get_remote_size()
        file_size = os.path.getsize(self.local)
        if file_size > remote_size:
            return False

        return True

    def local_file_exists(self):
        return os.path.isfile(self.local)

    def remote_file_exists(self):
        try:
            self.device.show('dir {}'.format(self.remote))
        except:
            return False

        return True

    def get_local_md5(self, blocksize=2**20):
        if self.local_file_exists():
            m = hashlib.md5()
            with open(self.local, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    def get_remote_md5(self):
        try:
            hash_out = self.device.show('verify /md5 {}'.format(self.remote), raw_text=True)
            hash_out = hash_out.split('=')[1].strip()
            return hash_out
        except:
            return None

    def already_transfered(self):
        remote_hash = self.get_remote_md5()
        local_hash = self.get_local_md5()
        if local_hash is not None:
            if local_hash == remote_hash:
                return True

        return False

    def transfer_file(self, pull=False):
        if pull is False:
            if not self.local_file_exists():
                raise FileTransferError(
                    'Could not transfer file. Local file doesn\'t exist.')

            if not self.enough_remote_space():
                raise FileTransferError(
                    'Could not transfer file. Not enough space on device.')

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self.device.host,
            username=self.device.username,
            password=self.device.password,
            port=self.port,
            allow_agent=False,
            look_for_keys=False)

        scp = SCPClient(ssh.get_transport(), socket_timeout=30.0)
        try:
            if pull:
                scp.get(self.remote, self.local)
            else:
                scp.put(self.local, self.remote)
        except Exception as e:
            raise FileTransferError
        finally:
            scp.close()

        return True

    def send(self):
        self.transfer_file()

    def get(self):
        self.transfer_file(pull=True)
