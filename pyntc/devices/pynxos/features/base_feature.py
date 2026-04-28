class BaseFeature(object):
    def __init__(self, device):
        self.device = device

    def get(self, vlan_id):
        raise NotImplementedError

    def get_list(self):
        raise NotImplementedError

    def get_all(self):
        raise NotImplementedError

    def config(self, vlan_id, **params):
        raise NotImplementedError

    def remove(self, vlan_id):
        raise NotImplementedError
