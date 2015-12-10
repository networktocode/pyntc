class BaseDevice(object):
    def __init__(self, vendor, device_type, host, username, password, **kwargs):
        self.vendor = vendor
        self.device_type = device_type
        self.host = host
        self.username = username
        self.password = password

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