class BaseDevice(object):
    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def config(self, command):
        raise NotImplementedError

    def show(self, command):
        raise NotImplementedError

    def save(self):
        raise NotImplementedError

    @property
    def facts(self):
        raise NotImplementedError

    @property
    def running_conig(self):
        raise NotImplementedError