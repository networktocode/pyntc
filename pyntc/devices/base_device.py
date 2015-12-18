import importlib

from pyntc.errors import FeatureNotFoundError

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