class NTCError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return "%s: \n%s" % (self.__class__.__name__, self.message)

    __str__ = __repr__


class UnsupportedDeviceError(NTCError):
    def __init__(self, vendor):
        message = "%s is not a supported vendor." % vendor
        super().__init__(message)


class DeviceNameNotFoundError(NTCError):
    def __init__(self, name, filename):
        message = "Name %s not found in %s. The file may not exist." % (name, filename)
        super().__init__(message)


class ConfFileNotFoundError(NTCError):
    def __init__(self, filename):
        message = "NTC Configuration file %s could not be found." % filename
        super().__init__(message)


class CommandError(NTCError):
    def __init__(self, command, message):
        self.cli_error_msg = message
        message = "Command %s was not successful: %s" % (command, message)
        super().__init__(message)


class CommandListError(NTCError):
    def __init__(self, commands, command, message):
        self.commands = commands
        self.command = command
        message = "\nCommand %s failed with message: %s" % (command, message)
        message += "\nCommand List: \n"
        for command in commands:
            message += "\t%s\n" % command
        super().__init__(message)


class FeatureNotFoundError(NTCError):
    def __init__(self, feature, device_type):
        message = "%s feature not found for %s device type." % (feature, device_type)
        super().__init__(message)


class FileSystemNotFoundError(NTCError):
    def __init__(self, hostname, command):
        message = 'Unable to parse "{0}" command to identify the default file system on {1}.'.format(command, hostname)
        super().__init__(message)


class RebootTimeoutError(NTCError):
    def __init__(self, hostname, wait_time):
        message = "Unable to reconnect to {0} after {1} seconds".format(hostname, wait_time)
        super().__init__(message)


class NotEnoughFreeSpaceError(NTCError):
    def __init__(self, hostname, min_space):
        message = "{0} does not meet the minimum disk space requirements of {1}".format(hostname, min_space)
        super().__init__(message)


class OSInstallError(NTCError):
    def __init__(self, hostname, desired_boot):
        message = "{0} was unable to boot into {1}".format(hostname, desired_boot)
        super().__init__(message)


class NTCFileNotFoundError(NTCError):
    def __init__(self, hostname, file, dir):
        message = "{0} was not found in {1} on {2}".format(file, dir, hostname)
        super().__init__(message)


class WLANEnableError(NTCError):
    def __init__(self, hostname, desired_wlans, actual_wlans):
        message = (
            f"Unable to enable WLAN IDs on {hostname}\n"
            f"Expected: {sorted(desired_wlans)}\n"
            f"Found:    {sorted(actual_wlans)}\n"
        )
        super().__init__(message)


class WLANDisableError(NTCError):
    def __init__(self, hostname, desired_wlans, actual_wlans):
        message = (
            f"Unable to disable WLAN IDs on {hostname}\n"
            f"Expected: {sorted(desired_wlans)}\n"
            f"Found:    {sorted(actual_wlans)}\n"
        )
        super().__init__(message)
