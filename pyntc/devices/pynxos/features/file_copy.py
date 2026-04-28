from scp import SCPClient
from pyntc.devices.pynxos.errors import CLIError, NXOSError

import paramiko
import hashlib
import os
import re


class FileTransferError(NXOSError):
    pass


class FileCopy(object):
    """This class is used to copy local files to a NXOS device."""

    def __init__(self, device, src, dst=None, port=22, file_system="bootflash:"):
        self.device = device
        self.src = src
        self.dst = dst or os.path.basename(src)
        self.port = port
        self.file_system = file_system

    def get_flash_size(self):
        """Return the available space in the remote directory."""
        dir_out = self.device.show("dir {}".format(self.file_system), raw_text=True)

        match = re.search(r"(\d+) bytes free", dir_out)
        bytes_free = match.group(1)

        return int(bytes_free)

    def get_remote_size(self):
        return self.get_flash_size()

    def enough_space(self):
        """Check for enough space on the remote device."""
        flash_size = self.get_flash_size()
        file_size = os.path.getsize(self.src)
        if file_size > flash_size:
            return False

        return True

    def enough_remote_space(self):
        return self.enough_space()

    def local_file_exists(self):
        return os.path.isfile(self.src)

    def file_already_exists(self):
        """Check to see if there is a remote file with the same
        name and md5 sum.

        Returns:
            ``True`` if exists, ``False`` otherwise.
        """
        dst_hash = self.get_remote_md5()
        src_hash = self.get_local_md5()
        if src_hash == dst_hash:
            return True

        return False

    def already_transfered(self):
        return self.file_already_exists()

    def remote_file_exists(self):
        dir_body = self.device.show("dir {0}/{1}".format(self.file_system, self.dst), raw_text=True)
        if "No such file" in dir_body:
            return False

        return True

    def get_remote_md5(self):
        """Return the md5 sum of the remote file,
        if it exists.
        """
        md5_body = self.device.show("show file {0}{1} md5sum".format(self.file_system, self.dst), raw_text=True)
        return md5_body.strip()

    def get_local_md5(self, blocksize=2**20):
        """Get the md5 sum of the local file,
        if it exists.
        """
        if self.local_file_exists():
            m = hashlib.md5()
            with open(self.src, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    def transfer_file(self, hostname=None, username=None, password=None, pull=False):
        """Transfer the file to the remote device over SCP.

        Note:
            If any arguments are omitted, the corresponding attributes
            of ``self.device`` will be used.

        Args:
            hostname (str): OPTIONAL - The name or
                IP address of the remote device.
            username (str): OPTIONAL - The SSH username
                for the remote device.
            password (str): OPTIONAL - The SSH password
                for the remote device.

        Returns:
            True if successful.

        Raises:
            FileTransferError: if the transfer isn't successful.
        """
        if pull is False:
            if not self.local_file_exists():
                raise FileTransferError("Could not transfer file. Local file doesn't exist.")

            if not self.enough_space():
                raise FileTransferError("Could not transfer file. Not enough space on device.")

        hostname = hostname or self.device.host
        username = username or self.device.username
        password = password or self.device.password

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=hostname,
            username=username,
            password=password,
            port=self.port,
            allow_agent=False,
            look_for_keys=False,
        )

        full_remote_path = "{}{}".format(self.file_system, self.dst)
        scp = SCPClient(ssh.get_transport())
        try:
            if pull:
                scp.get(full_remote_path, self.src)
            else:
                scp.put(self.src, full_remote_path)
        except:
            raise FileTransferError(
                "Could not transfer file. There was an error during transfer. Please make sure remote permissions are set."
            )
        finally:
            scp.close()

        return True

    def send(self):
        self.transfer_file()

    def get(self):
        self.transfer_file(pull=True)
