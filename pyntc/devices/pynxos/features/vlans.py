from pyntc.devices.pynxos.lib.data_model.converters import converted_list_from_table
from pyntc.devices.pynxos.lib.data_model.key_maps import VLAN_KEY_MAP

from .base_feature import BaseFeature


class Vlans(BaseFeature):
    def __init__(self, device):
        super(Vlans, self).__init__(device)


    def get_list(self):
        all_vlan_list = self.get_all()
        vlan_id_list = list(str(x["id"]) for x in all_vlan_list)

        return vlan_id_list

    def get_all(self):
        all_vlan_table = self.device.show("show vlan")
        all_vlan_list = converted_list_from_table(all_vlan_table, "vlanbrief", VLAN_KEY_MAP)

        return all_vlan_list
