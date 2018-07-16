import abc
import os
import hashlib
from pyntc.errors import NTCError


class FileTransferError(NTCError):
    def __init__(self, message=None):
        if message is None:
            message = 'An error occured during transfer. Please make sure the local file exists ' \
                      'and that appropriate permissions are set on the remote device.'
        super(FileTransferError, self).__init__(message)


class BaseFileCopy(object):
    """
    TODO: Add comments to methods
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, device, local, remote=None, port=22):
        self.device = device
        self.local = local
        self.remote = remote or os.path.basename(local)
        self.port = port

    def already_transferred(self):
        remote_hash = self.get_remote_md5()
        local_hash = self.get_local_md5()
        if local_hash is not None:
            if local_hash == remote_hash:
                return True

        return False

    def enough_remote_space(self):
        remote_size = self.get_remote_size()
        file_size = os.path.getsize(self.local)
        if file_size > remote_size:
            return False

        return True

    def get(self):
        self.transfer_file(pull=True)

    def get_local_md5(self, blocksize=2**20):
        if self.local_file_exists():
            m = hashlib.md5()
            with open(self.local, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    @abc.abstractmethod
    def get_remote_md5(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_remote_size(self):
        raise NotImplementedError

    def local_file_exists(self):
        return os.path.isfile(self.local)

    @abc.abstractmethod
    def remote_file_exists(self):
        raise NotImplementedError

    def send(self):
        self.transfer_file()

    @abc.abstractmethod
    def transfer_file(self, pull=False):
        raise NotImplementedError
