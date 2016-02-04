import mock
import unittest

from .mocks.eos import get, getall
from pyntc.devices.system_features.vlans.eos_vlans import EOSVlans
from pyntc.devices.system_features.vlans.base_vlans import VlanNotInRangeError

class TestEOSVlan(unittest.TestCase):

    @mock.patch('pyeapi.api.vlans.Vlans', autospec=True)
    @mock.patch('pyeapi.client.Node', autospec=True)
    @mock.patch('pyntc.devices.eos_device.EOSDevice', autospec=True)
    def setUp(self, mock_eos_device, mock_native_node, mock_native_vlans):
        mock_eos_instance = mock_eos_device.return_value
        mock_eos_instance.native = mock_native_node

        mock_native_vlans.get.side_effect = get
        mock_native_vlans.getall.side_effect = getall

        self.vlans = EOSVlans(mock_eos_instance)
        self.vlans.native_vlans = mock_native_vlans

    def test_get(self):
        result = self.vlans.get('10')
        self.assertEqual(result.get('name'), 'VLAN0010')
        self.assertEqual(result.get('state'), 'active')
        self.assertEqual(result.get('id'), '10')

    def test_bad_get(self):
        with self.assertRaises(VlanNotInRangeError):
            self.vlans.get('6000')

    def test_get_list(self):
        result = self.vlans.get_list()
        self.assertEqual(result, ['1', '10'])

    def test_remove(self):
        self.vlans.remove('10')
        self.vlans.native_vlans.delete.assert_called_with('10')

if __name__ == "__main__":
    unittest.main()








