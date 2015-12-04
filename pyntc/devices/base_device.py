class BaseDevice(object):
    def __init__(self, host, username, password, **kwargs):
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

    def save(self):
        raise NotImplementedError

    @property
    def facts(self):
        raise NotImplementedError

    @property
    def running_conig(self):
        raise NotImplementedError