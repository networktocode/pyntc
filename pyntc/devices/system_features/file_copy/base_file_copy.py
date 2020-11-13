from ..base_feature import BaseFeature
from pyntc.errors import NTCError


class BaseFileCopy(BaseFeature):
    pass


class FileTransferError(NTCError):
    default_message = (
        "An error occurred during transfer. "
        "Please make sure the local file exists and "
        "that appropriate permissions are set on the remote device."
    )

    def __init__(self, message=None):
        super().__init__(message or self.default_message)
