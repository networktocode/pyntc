import abc
import importlib

from pyntc.errors import NTCError, FeatureNotFoundError

class SetBootImageError(NTCError):
    pass

class RollbackError(NTCError):
    pass

class FileTransferError(NTCError):
    pass

class BaseDevice(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, host, username, password, vendor=None, device_type=None, **kwargs):
        self.host = host
        self.username = username
        self.password = password
        self.vendor = vendor
        self.device_type = device_type

    @abc.abstractmethod
    def open(self):
        """Open a connection to the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def close(self):
        """Close the connectin to the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def config(self, command):
        """Send a configuration command.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def config_list(self, commands):
        """Send a list of configuration commands.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def show(self, command):
        """Send a non-configuration command.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def show_list(self, commands):
        """Send a list of non-configuration commands.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def save(self, filename=None):
        """Save a devices running configuration.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def file_copy(self, src, dest=None):
        """Send a local file to the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def file_copy_remote_exists(self, src, dest=None):
        """Check if a remote file exists.
        """

    @abc.abstractmethod
    def reboot(self, timer=0, confirm=False):
        """Reboot the device.

        Args:
            confirm(bool): if False, this method has no effect
            timer(int): number of seconds to wait before rebooting
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_boot_options(self):
        """Get current boot variables
        like system image and kickstart image.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def set_boot_options(self, image_name, **vendor_specifics):
        """Set boot variables
        like system image and kickstart image.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def checkpoint(self, filename):
        """Save a checkpoint of the running configuration to the device.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self, checkpoint_file):
        """Rollback to a checkpoint file.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def backup_running_config(self, filename):
        """Save a local copy of the running config.
        """
        raise NotImplementedError

    @abc.abstractproperty
    def facts(self):
        raise NotImplementedError

    @abc.abstractproperty
    def running_config(self):
        raise NotImplementedError

    @abc.abstractproperty
    def startup_config(self):
        raise NotImplementedError

    def refresh_facts(self):
        """Refresh cached facts.
        """
        del self._facts
        self.facts

    def refresh(self):
        """Refresh caches on device instance.
        """
        self.refresh_facts()

    def feature(self, feature_name):
        """Return a feature class based on the ``feature_name`` for the
        appropriate subclassed device type.
        """
        try:
            feature_module = importlib.import_module(
                'pyntc.features.%s.%s_%s' % (feature_name, self.device_type, feature_name))
            return feature_module.instance(self)
        except ImportError:
            raise FeatureNotFoundError(feature_name, self.device_type)
        except AttributeError:
            raise
