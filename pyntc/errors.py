class NTCError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return '%s: \n%s' % (self.__class__.__name__, self.message)

    __str__ = __repr__


class UnsupportedDeviceError(NTCError):
    def __init__(self, vendor):
        message = '%s is not a supported vendor.' % vendor
        super(UnsupportedDeviceError, self).__init__(message)


class DeviceNameNotFoundError(NTCError):
    def __init__(self, name, filename):
        message = 'Name %s not found in %s. The file may not exist.' % (name, filename)
        super(DeviceNameNotFoundError, self).__init__(message)


class ConfFileNotFoundError(NTCError):
    def __init__(self, filename):
        message = 'NTC Configuration file %s could not be found.' % filename
        super(ConfFileNotFoundError, self).__init__(message)


class CommandError(NTCError):
    def __init__(self, command, message):
        self.cli_error_msg = message
        message = 'Command %s was not successful: %s' % (command, message)
        super(CommandError, self).__init__(message)


class CommandListError(NTCError):
    def __init__(self, commands, command, message):
        self.commands = commands
        self.command = command
        message = '\nCommand %s failed with message: %s' % (command, message)
        message += '\nCommand List: \n'
        for command in commands:
            message += '\t%s\n' % command
        super(CommandListError, self).__init__(message)


class FeatureNotFoundError(NTCError):
    def __init__(self, feature, device_type):
        message = '%s feature not found for %s device type.' % (feature, device_type)
        super(FeatureNotFoundError, self).__init__(message)
