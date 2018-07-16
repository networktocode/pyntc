import paramiko
import re
from scp import SCPClient
from .base_file_copy import BaseFileCopy, FileTransferError


class EOSFileCopy(BaseFileCopy):

    def get_remote_md5(self):
        try:
            hash_out = self.device.show('verify /md5 {}'.format(self.remote), raw_text=True)
            hash_out = hash_out.split('=')[1].strip()
            return hash_out
        # TODO: Determine correct exceptions to catch
        except:
            return None

    def get_remote_size(self):
        dir_out = self.device.show('dir', raw_text=True)
        match = re.search(r'(\d+) bytes free', dir_out)
        bytes_free = match.group(1)

        return int(bytes_free)

    def remote_file_exists(self):
        try:
            self.device.show('dir {}'.format(self.remote))
        # TODO: Determine correct exceptions to catch
        except:
            return False

        return True

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
        except Exception:
            raise FileTransferError
        finally:
            scp.close()

        return True
