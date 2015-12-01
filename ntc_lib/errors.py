class NTCError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return '%s: %s' % (self.__class__.__name__, self.message)

    __str__ = __repr__

class UnsupportedDeviceError(NTCError):
    def __init__(self, vendor):
        message = '%s is not a supported vendor.' % vendor
        super(self.__class__, self).__init__(message)
