class NTCError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return '%s: %s' % (self.__class__.__name__, self.message)

    __str__ = __repr__

class UnsupportedDeviceError(NTCError):
    def __init__(self, vendor):
        message = '%s is not a supported vendor.' % vendor
        super(UnsupportedDeviceError, self).__init__(message)

class DeviceNameNotFoundError(NTCError):
    def __init__(self, name, filename):
        message = 'Name %s not found in %s. The file may not exist.' % (name, filename)
        super(DeviceNameNotFoundError, self).__init__(message)

class CommandError(NTCError):
    def __init__(self, message):
        message = 'Command was not successful: %s' % message
        super(CommandError, self).__init__(message)

class FeatureNotFoundError(NTCError):
    def __init__(self, feature, device_type):
        message = '%s feature not found for %s device type.' % (feature, device_type)
        super(FeatureNotFoundError, self).__init__(message)
