from pyntc.devices.pynxos.lib.data_model.converters import converted_list_from_table
from pyntc.devices.pynxos.lib.data_model.key_maps import VLAN_KEY_MAP
from pyntc.devices.pynxos.errors import NXOSError

from .base_feature import BaseFeature

# class VlanNotInRangeError(NXOSError):
#    def __init__(self):
#        super(VlanNotInRangeError, self).__init__(
#            'Vlan Id must be in range 1-3967')
#
# def vlan_not_in_range_error(vlan_id):
#    vlan_id = int(vlan_id)
#
#    if vlan_id < 1 or vlan_id > 3967:
#        raise VlanNotInRangeError


class Vlans(BaseFeature):
    def __init__(self, device):
        super(Vlans, self).__init__(device)

    #    def get(self, vlan_id):
    #        vlan_not_in_range_error(vlan_id)
    #
    #        vlan_id_table = self.device.show('show vlan id %s' % vlan_id)
    #        try:
    #            return converted_list_from_table(
    #                vlan_id_table, 'vlanbriefid', VLAN_KEY_MAP)[0]
    #        except IndexError:
    #            return {}

    def get_list(self):
        all_vlan_list = self.get_all()
        vlan_id_list = list(str(x["id"]) for x in all_vlan_list)

        return vlan_id_list

    def get_all(self):
        all_vlan_table = self.device.show("show vlan")
        all_vlan_list = converted_list_from_table(all_vlan_table, "vlanbrief", VLAN_KEY_MAP)

        return all_vlan_list


#    def config(self, vlan_id, **params):
#        vlan_not_in_range_error(vlan_id)
#
#        vlan_config_commands = ['vlan %s' % vlan_id]
#        vlan_name = params.get('name')
#        if vlan_name:
#            vlan_config_commands.append('name %s' % vlan_name)
#
#        self.device.config_list(vlan_config_commands)
#
#    def set_name(self, vlan_id, vlan_name=None, default=False, disable=False):
#        vlan_not_in_range_error(vlan_id)
#
#        vlan_config_commands = ['vlan %s' % vlan_id]
#        if vlan_name is None:
#            if default or disable:
#                name_command = 'no name'
#            else:
#                raise NXOSError('vlan_name must be supplied, or default or disable set to True')
#        else:
#            name_command = 'name %s' % vlan_name
#
#        vlan_config_commands.append(name_command)
#        self.device.config_list(vlan_config_commands)
#
#    def remove(self, vlan_id):
#        vlan_not_in_range_error(vlan_id)
#
#        vlan_remove_command = 'no vlan %s' % vlan_id
#        self.device.config(vlan_remove_command)
#
# def instance(device):
#    return Vlans(device)
