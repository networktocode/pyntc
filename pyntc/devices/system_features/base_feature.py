class BaseFeature(object):
    def config(self, vlan_id, **params):
        raise NotImplementedError

    def get_all(self):
        raise NotImplementedError

    def get(self, vlan_id):
        raise NotImplementedError

    def get_list(self):
        raise NotImplementedError
