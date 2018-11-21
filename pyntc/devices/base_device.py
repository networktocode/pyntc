"""The module contains the base class that all device classes must inherit from.
"""

import abc
import importlib

from pyntc.errors import NTCError, FeatureNotFoundError


def fix_docs(cls):
    for name, func in vars(cls).items():
        if hasattr(func, "__call__") and not func.__doc__:
            # print(func, 'needs doc')
            for parent in cls.__bases__:
                parfunc = getattr(parent, name, None)
                if parfunc and getattr(parfunc, "__doc__", None):
                    func.__doc__ = parfunc.__doc__
                    break
    return cls


class BaseDevice(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, host, username, password, vendor=None, device_type=None, **kwargs):
        self.host = host
        self.username = username
        self.password = password
        self.vendor = vendor
        self.device_type = device_type
        self._facts = None

    def _image_booted(self, image_name, **vendor_specifics):
        """Determines if a particular image is serving as the active OS.

        Args:
            image_name (str): The image that you would like the device to be using for active OS.
            vendor_specifics (kwargs):
                volume: Required by F5Device as F5 boots into a volume.

        Returns:
            bool: True if image is currently being used by the device, else False.
        """
        raise NotImplementedError

    ####################
    # ABSTRACT METHODS #
    ####################
    @abc.abstractmethod
    def backup_running_config(self, filename):
        """Save a local copy of the running config.

        Args:
            filename (str): The local file path on which to save the running config.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def checkpoint(self, filename):
        """Save a checkpoint of the running configuration to the device.

        Args:
            filename (str): The filename to save the checkpoint as on the remote device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def close(self):
        """Close the connection to the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def config(self, command):
        """Send a configuration command.

        Args:
            command (str): The command to send to the device.

        Raises:
            CommandError: If there is a problem with the supplied command.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def config_list(self, commands):
        """Send a list of configuration commands.

        Args:
            commands (list): A list of commands to send to the device.

        Raises:
            CommandListError: If there is a problem with one of the commands in the list.
        """
        raise NotImplementedError

    @abc.abstractproperty
    def facts(self):
        """Return a dictionary of facts about the device.

        The dictionary must include the following keys.
        All keys are strings, the value type is given in parenthesis:
            uptime (int)
            vendor (str)
            os_version (str)
            interfaces (list of strings)
            hostname (str)
            fqdn (str)
            uptime_string (str)
            serial_number (str)
            model (str)
            vlans (list of strings)

        The dictionary can also include a vendor-specific dictionary, with the
        device type as a key in the outer dictionary.

        Example:
            {
                "uptime": 1819711,
                "vendor": "cisco",
                "os_version": "7.0(3)I2(1)",
                "interfaces": [
                    "mgmt0",
                    "Ethernet1/1",
                    "Ethernet1/2",
                    "Ethernet1/3",
                    "Ethernet1/4",
                    "Ethernet1/5",
                    "Ethernet1/6",
                ],
                "hostname": "n9k1",
                "fqdn": "N/A",
                "uptime_string": "21:01:28:31",
                "serial_number": "SAL1819S6LU",
                "model": "Nexus9000 C9396PX Chassis",
                "vlans": [
                    "1",
                    "2",
                    "3",
                ]
            }
        """
        raise NotImplementedError

    @abc.abstractmethod
    def file_copy(self, src, dest=None, **kwargs):
        """Send a local file to the device.

        Args:
            src (str): Path to the local file to send.
            dest (str): The destination file path to be saved on remote flash.
                If none is supplied, the implementing class should use the basename
                of the source path.

        Keyword Args:
            file_system (str): Supported only for IOS and NXOS. The file system for the
                remote fle. If no file_system is provided, then the ``get_file_system``
                method is used to determine the correct file system to use.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        """Check if a remote file exists.

        A remote file exists if it has the same name as supplied dest,
        and the same md5 hash as the source.

        Args:
            src (str): Path to local file to check.
            dest (str): The destination file path to be saved on remote the remote device.
                If none is supplied, the implementing class should use the basename
                of the source path.

        Keyword Args:
            file_system (str): Supported only for IOS and NXOS. The file system for the
                remote fle. If no file_system is provided, then the ``get_file_system``
                method is used to determine the correct file system to use.

        Returns:
            True if the remote file exists, False if it doesn't.
        """

    @abc.abstractmethod
    def get_boot_options(self):
        """Get current boot variables
        like system image and kickstart image.

        Returns:
            A dictionary, e.g. {'kick': router_kick.img, 'sys': 'router_sys.img'}
        """
        raise NotImplementedError

    @abc.abstractmethod
    def install_os(self, image_name, **vendor_specifics):
        """Install the OS from specified image_name

        Args:
            image_name(str): The name of the image on the device to install.

        Keyword Args:
            kickstart (str): Option for ``NXOSDevice`` for devices that require a kickstart image.
            volume (str): Option for ``F5Device`` to set the target boot volume.
            file_system (str): Option for ``ASADevice``, ``EOSDevice``, ``IOSDevice``, and
                ``NXOSDevice`` to set where the OS files are stored. The default will use
                the ``_get_file_system`` method.
            timeout (int): Option for ``IOSDevice`` and ``NXOSDevice`` to set the wait time for
                device installation to complete.

        Returns:
            True if system has been installed during function's call, False if OS has not been installed

        Raises:
            OSInstallError: When device finishes installation process, but the running image
                does not match ``image_name``.
            CommandError: When sending a command to the device fails, or when the config status
                after sending a command does not yield expected results.
            CommandListError: When sending commands to the device fails.
            NotEnoughFreeSpaceError: When the device does not have enough free space for install.
            NTCFileNotFoundError: When the ``image_name`` is not found in the devices ``file_system``.
            FileSystemNotFoundError: When the ``file_system`` is left to default,
                and the ``file_system`` cannot be identified.
            RebootTimeoutError: When device is rebooted and is unreachable longer than ``timeout`` period.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def open(self):
        """Open a connection to the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def reboot(self, timer=0, confirm=False):
        """Reboot the device.

        Args:
            confirm(bool): if False, this method has no effect.
            timer(int): number of seconds to wait before rebooting.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self, checkpoint_file):
        """Rollback to a checkpoint file.

        Args:
            filename (str): The filename of the checkpoint file to load into the running configuration.
        """
        raise NotImplementedError

    @abc.abstractproperty
    def running_config(self):
        """Return the running configuration of the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def save(self, filename=None):
        """Save a device's running configuration.

        Args:
            filename (str): The filename on the remote device.
                If none is supplied, the implementing class should
                save to the "startup configuration".
        """
        raise NotImplementedError

    @abc.abstractmethod
    def set_boot_options(self, image_name, **vendor_specifics):
        """Set boot variables
        like system image and kickstart image.

        Args:
            image_name: The main system image file name.

        Keyword Args:
            kickstart: Option for ``NXOSDevice`` for devices that require a kickstart image.
            volume: Option for ``F5Device`` to set which volume should have image installed.
            file_system: Option for ``ASADevice`` and ``IOSDevice`` to set which directory
                to use when setting the boot path. The default will use the directory returned
                by the ``_get_file_system()`` method.

        Raises:
            ValueError: When the boot options returned by the ``get_boot_options``
                method does not match the ``image_name`` after the config command(s)
                have been sent to the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def show(self, command, raw_text=False):
        """Send a non-configuration command.

        Args:
            command (str): The command to send to the device.

        Keyword Args:
            raw_text (bool): Whether to return raw text or structured data.

        Returns:
            The output of the show command, which could be raw text or structured data.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def show_list(self, commands, raw_text=False):
        """Send a list of non-configuration commands.

        Args:
            commands (list): A list of commands to send to the device.

        Keyword Args:
            raw_text (bool): Whether to return raw text or structured data.

        Returns:
            A list of outputs for each show command
        """
        raise NotImplementedError

    @abc.abstractproperty
    def startup_config(self):
        """Return the startup configuration of the device.
        """
        raise NotImplementedError

    #################################
    # Inherited implemented methods #
    #################################

    def feature(self, feature_name):
        """Return a feature class based on the ``feature_name`` for the
        appropriate subclassed device type.
        """
        try:
            feature_module = importlib.import_module(
                "pyntc.devices.system_features.%s.%s_%s" % (feature_name, self.device_type, feature_name)
            )
            return feature_module.instance(self)
        except ImportError:
            raise FeatureNotFoundError(feature_name, self.device_type)
        except AttributeError:
            raise

    def refresh(self):
        """Refresh caches on device instance.
        """
        self.refresh_facts()

    def refresh_facts(self):
        """Refresh cached facts.
        """
        # Persist values that were not added by facts getter
        if isinstance(self._facts, dict):
            facts_backup = self._facts.copy()
            self._facts = None
            facts_backup.update(self.facts)
            self._facts = facts_backup.copy()
        else:
            self._facts = None

        return self.facts


class FileTransferError(NTCError):
    pass


class RebootTimerError(NTCError):
    def __init__(self, device_type):
        super(RebootTimerError, self).__init__("Reboot timer not supported on %s." % device_type)


class RollbackError(NTCError):
    pass


class SetBootImageError(NTCError):
    pass
