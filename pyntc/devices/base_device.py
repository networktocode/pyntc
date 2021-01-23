"""The module contains the base class that all device classes must inherit from."""

import abc
import importlib
import warnings


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
    """Base Device ABC."""

    __metaclass__ = abc.ABCMeta

    def __init__(self, host, username, password, device_type=None, **kwargs):
        self.host = host
        self.username = username
        self.password = password
        self.device_type = device_type
        self._uptime = None
        self._os_version = None
        self._interfaces = None
        self._hostname = None
        self._fqdn = None
        self._uptime_string = None
        self._serial_number = None
        self._model = None
        self._vlans = None

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

    @property
    @abc.abstractmethod
    def boot_options(self):
        """Get current boot variables
        like system image and kickstart image.

        Returns:
            A dictionary, e.g. {'kick': router_kick.img, 'sys': 'router_sys.img'}
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
        """Close the connection to the device."""
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

    @property
    @abc.abstractmethod
    def uptime(self):
        """Uptime integer property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def os_version(self):
        """Operating System string property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def interfaces(self):
        """Interfaces list of strings property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def hostname(self):
        """Host name string property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def fqdn(self):
        """fqdn name string property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def uptime_string(self):
        """Uptime string string property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def serial_number(self):
        """Serial number string property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def model(self):
        """Model string property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def vlans(self):
        """Vlans lost of strings property, part of device facts.

        Raises:
            NotImplementedError: returns not implemented if not included in facts.
        """
        raise NotImplementedError

    def facts(self):
        warnings.warn("facts() is deprecated; use individual fact properties.", DeprecationWarning)
        facts = {
            fact: getattr(self, fact, None)
            for fact in [
                "vendor",
                "uptime",
                "uptime_string",
                "hostname",
                "fqdn",
                "interfaces",
                "vlans",
                "model",
                "serial_number",
                "os_version",
            ]
        }
        if self.device_type == "cisco_ios_ssh":
            facts[self.device_type] = {"config_register": self.config_register}

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
        """Open a connection to the device."""
        raise NotImplementedError

    @abc.abstractmethod
    def reboot(self, timer=0):
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

    @property
    @abc.abstractmethod
    def running_config(self):
        """Return the running configuration of the device."""
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
            ValueError: When the boot options returned by the ``boot_options``
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

    @property
    @abc.abstractmethod
    def startup_config(self):
        """Return the startup configuration of the device."""
        raise NotImplementedError

    #################################
    # Inherited implemented methods #
    #################################

    def feature(self, feature_name):
        """Return a feature class based on the ``feature_name`` for the
        appropriate subclassed device type."""
        try:
            feature_module = importlib.import_module(
                "pyntc.devices.system_features.%s.%s_%s" % (feature_name, self.device_type, feature_name)
            )
            return feature_module.instance(self)
        except ImportError:
            raise FeatureNotFoundError(feature_name, self.device_type)
        except AttributeError:
            raise

    def get_boot_options(self):
        """Get current boot variables
        like system image and kickstart image.

        Returns:
            A dictionary, e.g. {'kick': router_kick.img, 'sys': 'router_sys.img'}
        """
        warnings.warn("get_boot_options() is deprecated; use boot_options property.", DeprecationWarning)
        return self.boot_options

    def refresh(self):
        """Refresh caches on device instance."""
        self.refresh_facts()

    def refresh_facts(self):
        """Refresh cached facts."""
        # Persist values that were not added by facts getter
        if self.uptime:
            self._uptime = None

        if self.os_version:
            self._os_version = None

        if self.interfaces:
            self._interfaces = None

        if self.hostname:
            self._hostname = None

        if self.fqdn:
            self._fqdn = None

        if self.uptime_string:
            self._uptime_string = None

        if self.serial_number:
            self._serial_number = None

        if self.model:
            self._model = None

        if self.vlans:
            self._vlans = None

        return None


class RebootTimerError(NTCError):
    def __init__(self, device_type):
        super().__init__("Reboot timer not supported on %s." % device_type)


class RollbackError(NTCError):
    pass


class SetBootImageError(NTCError):
    pass
