from .base_vlans import BaseVlans
from pyntc.data_model.key_maps.eos_key_maps import VLAN_KM
from pyntc.data_model.converters import convert_dict_by_key


class EOSVlans(BaseVlans):

    def __init__(self, device):
        self.device = device

    def get(self, vlan_id):
        vlan_id = str(vlan_id)
        native_vlan_response = self.device.show(
            'show vlan id %s' % vlan_id)['vlans'][vlan_id]
        converted = convert_dict_by_key(native_vlan_response, VLAN_KM)
        converted['id'] = vlan_id

        return converted

    def list(self):
        native_vlan_list_response = self.device.show('show vlan')['vlans']
        extracted_vlan_ids = native_vlan_list_response.keys()

        return extracted_vlan_ids

    def config(self, vlan_id, **params):
        vlan_config_commands = ['vlan %s' % vlan_id]
        vlan_name = params.get('name')
        if vlan_name:
            vlan_config_commands.append('name %s' % vlan_name)

        self.device.config_list(vlan_config_commands)


def instance(device):
    return EOSVlans(device)
