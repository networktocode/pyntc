import unittest
from mock import Mock

from pyntc.devices import NXOSDevice

class TestNXOSDevice(unittest.TestCase):
    def setUp(self):
        self.device = NXOSDevice('host', 'user', 'pass')
        self.device.native = Mock()

    def test_config(self):
        command = 'interface Eth1/2'
        self.device.native.config = Mock(return_value=None)

        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with(command)

    def test_config_list(self):
        commands = ['interface Eth1/2', 'no shutdown']
        self.device.native.config_list = Mock(return_value=[None, None])

        result = self.device.config_list(commands)

        self.assertIsNone(result)
        self.device.native.config_list.assert_called_with(commands)

    def test_show(self):
        command = 'show ip arp'
        return_value = {u'TABLE_vrf': {u'ROW_vrf': {u'vrf-name-out': u'default', u'cnt-total': 0}}}
        self.device.native.show = Mock(return_value=return_value)

        result = self.device.show(command)

        self.assertEqual(result, return_value)
        self.device.native.show.assert_called_with(command, raw_text=False)

    def test_show_raw_text(self):
        command = 'show ip arp'
        return_value = u'N9K1.cisconxapi.com \n'
        self.device.native.show = Mock(return_value=return_value)

        result = self.device.show(command, raw_text=True)

        self.assertEquals(result, return_value)
        self.device.native.show.assert_called_with(command, raw_text=True)

    def test_show_list(self):
        commands = ['show ip arp', 'show hostname']
        return_value = [{u'TABLE_vrf': {u'ROW_vrf': {u'vrf-name-out': u'default', u'cnt-total': 0}}},
                        {u'hostname': u'N9K1.cisconxapi.com'}]
        self.device.native.show_list = Mock(return_value=return_value)

        result = self.device.show_list(commands)

        self.assertEquals(result, return_value)
        self.device.native.show_list.assert_called_with(commands, raw_text=False)