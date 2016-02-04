from ..base_feature import BaseFeature
from pyntc.errors import NTCError

class VlanNotInRangeError(NTCError):
    def __init__(self, lower, upper):
        super(VlanNotInRangeError, self).__init__(
            'Vlan Id must be in range %s-%s' % (lower, upper))

def vlan_not_in_range_error(vlan_id, lower=1, upper=4094):
    vlan_id = int(vlan_id)

    if vlan_id < lower or vlan_id > upper:
        raise VlanNotInRangeError(lower, upper)

class BaseVlans(BaseFeature):
    pass
