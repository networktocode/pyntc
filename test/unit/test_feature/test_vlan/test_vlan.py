import unittest
from pyntc import supported_devices, DEVICE_CLASS_KEY
from pyntc.data_model.schemas import validate

from test.unit.test_feature.test_vlan import mock_mapper

class TestVlan(unittest.TestCase):
    def __init__(self):
        super(TestVlan, self).__init__()

        self.devices = []
        for device_type in supported_devices:
            device = supported_devices[device_type][DEVICE_CLASS_KEY]('host', 'user', 'pass')
            device.native = mock_mapper[device_type].instance()

            mock_module = mock_mapper[device_type]

            self.devices.append(device)

    def test_get(self):
        for device in self.devices:
            vlans = device.feature('vlans')
            result = vlans.get('10')
            validate(result, 'vlan')

    def test_get_list(self):
        for device in self.devices:
            vlans = device.feature('vlans')
            result = vlans.get_list()

            validate(result, 'vlan_list')

    def test_config(self):
        for device in self.devices:
            vlans = device.feature('vlans')
            result = vlans.config('10', name='test vlan')

            self.assertIsNone(result)

    def test_get_bad(self):


    def test_config_bad(self):
        pass

    def test_config_with_name(self):

    def test_get_all(self):











