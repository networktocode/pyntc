from .base_vlans import BaseVlans, vlan_not_in_range_error
from pyntc.data_model.key_maps.nxos_key_maps import VLAN_KM
from pynxos.lib.data_model.converters import converted_list_from_table

UPPER_LIMIT = 3967

class NXOSVlans(BaseVlans):

    def __init__(self, device):
        self.device = device
        self.native_vlans = self.device.native.feature('vlans')

    def get(self, vlan_id):
        vlan_not_in_range_error(vlan_id, upper=UPPER_LIMIT)
        native_get_vlan = self.native_vlans.get(vlan_id)
        return native_get_vlan

    def get_list(self):
        native_get_list = self.native_vlans.get_list()
        return native_get_list

    def get_all(self):
        native_get_all = self.native_vlans.get_all()
        return native_get_all

    def config(self, vlan_id, **params):
        vlan_not_in_range_error(vlan_id, upper=UPPER_LIMIT)
        self.native_vlans.config(vlan_id, **params)

    def set_name(self, vlan_id, vlan_name, default=False, disable=False):
        vlan_not_in_range_error(vlan_id, upper=UPPER_LIMIT)
        self.native_vlans.set_name(vlan_id, vlan_name, default=default, disable=disable)

    def remove(self, vlan_id):
        vlan_not_in_range_error(vlan_id)
        self.native_vlans.remove(vlan_id)

def instance(device):
    return NXOSVlans(device)
