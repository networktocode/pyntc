"""Base Vlan checks."""
from pyntc.errors import NTCError

from ..base_feature import BaseFeature


def vlan_not_in_range_error(vlan_id, lower=1, upper=4094):
    """Validate vlan range."""
    vlan_id = int(vlan_id)
    if vlan_id < lower or vlan_id > upper:
        raise VlanNotInRangeError(lower, upper)


class BaseVlans(BaseFeature):
    """Subclass for base vlan feature."""

    pass


class VlanNotInRangeError(NTCError):
    """Vlan error.

    Args:
        NTCError (str): Vlan range error.
    """

    def __init__(self, lower, upper):
        """Exception for vlan range validation.

        Args:
            lower (int): lower vlan range.
            upper (int): upper vlan range.
        """
        super().__init__("Vlan Id must be in range %s-%s" % (lower, upper))
