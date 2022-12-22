"""Define base feature set."""


class BaseFeature(object):
    """Base feature sets."""

    def config(self, vlan_id, **params):
        """Base config feature."""
        raise NotImplementedError

    def get_all(self):
        """Base get all features."""
        raise NotImplementedError

    def get(self, vlan_id):
        """Base get feature."""
        raise NotImplementedError

    def get_list(self):
        """Base get_list feature."""
        raise NotImplementedError
