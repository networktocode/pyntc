from ..base_feature import BaseFeature
from pyntc.errors import NTCError

class FileTransferError(NTCError):
    def __init__(self, message=None):
        if message is None:
            message = 'An error occured during transfer. ' \
                      'Please make sure the local file exists and that appropriate permissions are set on the remote device.'
        super(FileTransferError, self).__init__(message)

class BaseFileCopy(BaseFeature):
    pass
