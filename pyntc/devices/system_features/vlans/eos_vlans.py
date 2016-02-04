from .base_vlans import BaseVlans, vlan_not_in_range_error
from pyntc.data_model.key_maps.eos_key_maps import VLAN_KM
from pyntc.data_model.converters import convert_dict_by_key, convert_list_by_key, strip_unicode

class EOSVlans(BaseVlans):

    def __init__(self, device):
        self.native_vlans = device.native.api('vlans')

    def get(self, vlan_id):
        vlan_not_in_range_error(vlan_id)

        vlan_id = str(vlan_id)
        native_vlan_response = self.native_vlans.get(vlan_id)
        converted = convert_dict_by_key(native_vlan_response, VLAN_KM)
        converted['id'] = vlan_id

        return strip_unicode(converted)

    def get_list(self):
        native_all_vlan_response = self.native_vlans.getall()
        extracted_vlan_ids = sorted(list(native_all_vlan_response.keys()))

        return strip_unicode(extracted_vlan_ids)

#    def get_all(self):
#        native_all_vlan_response = self.native_vlans.getall()
#        detailed_vlan_list = convert_list_by_key(native_all_vlan_response.values(), VLAN_KM)
#
#        return strip_unicode(detailed_vlan_list)

#    def config(self, vlan_id, **params):
#        vlan_not_in_range_error(vlan_id)
#
#        self.native_vlans.create(vlan_id)
#        vlan_name = params.get('name')
#        if vlan_name:
#            self.native_vlans.set_name(vlan_id, vlan_name)

#    def set_name(self, vlan_id, vlan_name, default=False, disable=False):
#        vlan_not_in_range_error(vlan_id)
#
#        self.native_vlans.set_name(
#            vlan_id, vlan_name, default=default, disable=disable)

    def remove(self, vlan_id):
        vlan_not_in_range_error(vlan_id)
        self.native_vlans.delete(vlan_id)

def instance(device):
    return EOSVlans(device)
