import importlib

from pyntc.errors import NTCError, FeatureNotFoundError

def SetBootImageError(NTCError):
    def __init__(self, message):
        super(SetBootImageError, self).__init__(message)

class BaseDevice(object):
    def __init__(self, host, username, password, vendor=None, device_type=None, **kwargs):
        self.host = host
        self.username = username
        self.password = password
        self.vendor = vendor
        self.device_type = device_type

    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def config(self, command):
        raise NotImplementedError

    def config_list(self, commands):
        raise NotImplementedError

    def show(self, command):
        raise NotImplementedError

    def show_list(self, commands):
        raise NotImplementedError

    def save(self, filename=None):
        raise NotImplementedError

    def file_copy(self, src, dest=None):
        raise NotImplementedError

    def reboot(self, timer=0, confirm=False):
        raise NotImplementedError

    def install_os(self, image_name, **vendor_specifics):
        raise NotImplementedError

    def checkpoint(self, filename):
        raise NotImplementedError

    def rollback(self, checkpoint=None, filename=None):
        raise NotImplementedError

    def backup_running_config(self, filename):
        raise NotImplementedError

    def refresh_facts(self):
        del self._facts
        self.facts

    def refresh(self):
        self.refresh_facts()

    @property
    def facts(self):
        raise NotImplementedError

    @property
    def running_conig(self):
        raise NotImplementedError

    @property
    def startup_config(self):
        raise NotImplementedError

    def feature(self, feature_name):
        try:
            feature_module = importlib.import_module(
                'pyntc.features.%s.%s_%s' % (feature_name, self.device_type, feature_name))
            return feature_module.instance(self)
        except ImportError:
            raise FeatureNotFoundError(feature_name, self.device_type)
        except AttributeError:
            raise
