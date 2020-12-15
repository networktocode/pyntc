import warnings


class NTCError(Exception):
    def __init__(self, message):
        """
        Generic Error class for PyNTC.

        Args:
            message (str): The error message associated with the Exception.
        """
        self.message = message

    def __repr__(self):
        return "%s: \n%s" % (self.__class__.__name__, self.message)

    __str__ = __repr__


class UnsupportedDeviceError(NTCError):
    def __init__(self, vendor):
        """
        Error class for Unsupported Devices.

        Args:
            vendor (str): The name of the deice's vendor to present in the error.
        """
        message = "%s is not a supported vendor." % vendor
        super().__init__(message)


class DeviceNameNotFoundError(NTCError):
    def __init__(self, name, filename):
        """
        Error for issues finding ``name`` in inventory file, ``filename``.

        Args:
            name (str): The hostname that failed the lookup.
            filename (str): The name of the file used for inventory.
        """
        message = "Name %s not found in %s. The file may not exist." % (name, filename)
        super().__init__(message)


class ConfFileNotFoundError(NTCError):
    def __init__(self, filename):
        """
        Error for issues finding the config ``filename``.

        Args:
            filename (str): The name of the file used for config settings.
        """
        message = "NTC Configuration file %s could not be found." % filename
        super().__init__(message)


class CommandError(NTCError):
    def __init__(self, command, message):
        """
        Error for issuing ``command`` on device.

        Args:
            command (str): The command that failed.
            message (str): The error message returned from the device.
        """
        self.command = command
        self.cli_error_msg = message
        message = "Command %s was not successful: %s" % (command, message)
        super().__init__(message)


class CommandListError(NTCError):
    def __init__(self, commands, command, message):
        """
        Error for issuing a ``command`` from a list of ``commands`` on device..

        Args:
            commands (list): The list of commands that were to be sent to the device.
            command (str): The command that reported an error on the device.
            message (str): The error emssage returned from the device.
        """
        warnings.warn("This will raise CommandError in the future", FutureWarning)
        self.commands = commands
        self.command = command
        message = "\nCommand %s failed with message: %s" % (command, message)
        message += "\nCommand List: \n"
        for command in commands:
            message += "\t%s\n" % command
        super().__init__(message)


class DeviceNotActiveError(NTCError):
    def __init__(self, hostname, redundancy_state, peer_redundancy_state):
        """
        Error for when the device is part of an HA cluster, and the device is not the active device.

        Args:
            hostname (str): The hostname of the device being validated.
        """
        message = (
            f"{hostname} is not the active device.\n\n"
            f"device state: {redundancy_state}\n"
            f"peer state:   {peer_redundancy_state}\n"
        )
        super().__init__(message)


class FeatureNotFoundError(NTCError):
    def __init__(self, feature, device_type):
        """
        Error for trying to use a PyNTC ``feature`` for an unsupported ``device_type``.

        Args:
            feature (str): The PyNTC feature name.
            device_type (str): The PyNTC device_type name.

        TODO: Remove this Exception when VLAN feature is removed.
        """
        message = "%s feature not found for %s device type." % (feature, device_type)
        super().__init__(message)


class FileSystemNotFoundError(NTCError):
    def __init__(self, hostname, command):
        """
        Error for inability to identify the default file system on network device.

        Args:
            hostname (str): The hostname of the device that failed.
            command (str): The command used to detect the default file system.
        """
        message = 'Unable to parse "{0}" command to identify the default file system on {1}.'.format(command, hostname)
        super().__init__(message)


class FileTransferError(NTCError):
    default_message = (
        "An error occurred during transfer. "
        "Please make sure the local file exists and "
        "that appropriate permissions are set on the remote device."
    )

    def __init__(self, message=None):
        super().__init__(message or self.default_message)


class RebootTimeoutError(NTCError):
    def __init__(self, hostname, wait_time):
        """
        Error for inability to log into device after waiting for max time for reboot to complete.

        Args:
            hostname (str): The hostname of the device that did not boot back up.
            wait_time (int): The amount of time waiting before considering the reboot failed.
        """
        message = "Unable to reconnect to {0} after {1} seconds".format(hostname, wait_time)
        super().__init__(message)


class NotEnoughFreeSpaceError(NTCError):
    def __init__(self, hostname, min_space):
        """
        Error for not having enough free space to transfer a file.

        Args:
            hostname (str): The hostname of the device that did not boot back up.
            min_space (str): The minimum amount of space required to transfer the file.
        """
        message = "{0} does not meet the minimum disk space requirements of {1}".format(hostname, min_space)
        super().__init__(message)


class OSInstallError(NTCError):
    def __init__(self, hostname, desired_boot):
        """
        Error for failing to install an OS on a device.

        Args:
            hostname (str): The hostname of the device that failed to install OS.
            desired_boot (str): The OS that was attempted to be installed.
        """
        message = "{0} was unable to boot into {1}".format(hostname, desired_boot)
        super().__init__(message)


class PeerFailedToFormError(NTCError):
    def __init__(self, hostname, desired_state, current_state):
        """
        Error for failing to have High Availability Peer form after state change.

        Args:
            hostname (str): The hostname of the device that did not peer properly.
            desired_state (str): The peer redundancy state that was expected.
            current_state (str): The current peer redundancy state of the device.
        """
        message = (
            f'{hostname} was unable to form a redundancy state of "{desired_state}" with peer.\n'
            f'The current state is "{current_state}".'
        )
        super().__init__(message)


class NTCFileNotFoundError(NTCError):
    def __init__(self, hostname, file, dir):
        """
        Error for not being able to find a file on a device.

        Args:
            hostname (str): The hostname of the device that did not have the ``file``.
            file (str): The name of the file that could not be found.
            dir (str): The directory on the network device where the file was searched for.

        TODO: Rename ``dir`` arg as that is a reserved name in python.
        """
        message = "{0} was not found in {1} on {2}".format(file, dir, hostname)
        super().__init__(message)


class SocketClosedError(NTCError):
    default_message = (
        "The device closed the connection during operation. Please make sure that you have remote access to the device."
    )

    def __init__(self, message=None):
        """
        Error for network device closing the socket connection during operation.

        Args:
            message (str): A custom error message to use instead of the default.
        """
        super().__init__(message or self.default_message)


class WLANEnableError(NTCError):
    def __init__(self, hostname, desired_wlans, actual_wlans):
        """
        Error for not being able to enable WLAN.

        Args:
            hostname (str): The hostname of the device that failed to enable all ``desired_wlans``.
            desired_wlans (list): The WLAN IDs that should have been enabled.
            actual_wlans (list): The WLAN IDs that are enabled on the device.
        """
        message = (
            f"Unable to enable WLAN IDs on {hostname}\n"
            f"Expected: {sorted(desired_wlans)}\n"
            f"Found:    {sorted(actual_wlans)}\n"
        )
        super().__init__(message)


class WLANDisableError(NTCError):
    def __init__(self, hostname, desired_wlans, actual_wlans):
        """
        Error for not being able to disable WLAN.

        Args:
            hostname (str): The hostname of the device that failed to disable all ``desired_wlans``.
            desired_wlans (list): The WLAN IDs that should have been disabled.
            actual_wlans (list): The WLAN IDs that are disabled on the device.
        """
        message = (
            f"Unable to disable WLAN IDs on {hostname}\n"
            f"Expected: {sorted(desired_wlans)}\n"
            f"Found:    {sorted(actual_wlans)}\n"
        )
        super().__init__(message)
