from .base_vlans import BaseVlans
from pyntc.data_model.key_maps.nxos_key_maps import VLAN_KM
from pynxos.lib.data_model.converters import converted_list_from_table

class NXOSVlans(BaseVlans):
    def __init__(self, device):
        self.device = device
        self._list = []

    def get(self, vlan_id):
        vlan_id_table = self.device.show('show vlan id %s' % vlan_id)
        try:
            return converted_list_from_table(vlan_id_table, 'vlanbriefid', VLAN_KM)[0]
        except IndexError:
            return {}

    def list(self):
        all_vlan_table = self.device.show('show vlan')
        all_vlan_list = converted_list_from_table(all_vlan_table, 'vlanbrief', VLAN_KM)
        vlan_id_list = list(x['id'] for x in all_vlan_list)

        return vlan_id_list

    def config(self, vlan_id, **params):
        vlan_config_commands = ['vlan %s' % vlan_id]
        vlan_name = params.get('name')
        if vlan_name:
            vlan_config_commands.append('name %s' % vlan_name)

        self.device.config_list(vlan_config_commands)


def instance(device):
    return NXOSVlans(device)