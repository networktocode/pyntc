import unittest
from mock import create_autospec
from pyntc import supported_devices, DEVICE_CLASS_KEY
from pyntc.data_model.schemas import validate

from test.unit.test_feature.test_vlan import mock_mapper


class TestNXOSVlan(unittest.TestCase):
    def setUp(self):
        self.devices = []
        for device_type in supported_devices:
            device = supported_devices[device_type][DEVICE_CLASS_KEY]('host', 'user', 'pass')
            device.native = mock_mapper[device_type]()
            self.devices.append(device)

    def test_show_vlan(self):
        for device in self.devices:
            vlans = device.feature('vlans')
            result = vlans.get('10')

            validate(result, 'vlan')

    def test_list_vlan(self):
        for device in self.devices:
            vlans = device.feature('vlans')
            result = vlans.list()

            validate(result, 'vlan_list')

    def test_config_vlan(self):
        for device in self.devices:
            vlans = device.feature('vlans')
            result = vlans.config('10')

            self.assertIsNone(result)









