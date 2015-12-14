class BaseFeature(object):
    def get(self, vlan_id):
        raise NotImplementedError

    def list(self):
        raise NotImplementedError

    def config(self, vlan_id, **params):
        raise NotImplementedError