import unittest
from mock import Mock

from pyntc.devices import EOSDevice

class TestEOSDevice(unittest.TestCase):
    def setUp(self):
        self.device = EOSDevice('host', 'user', 'pass')
        self.device.native = Mock()

    def test_config(self):
        command = 'interface Eth 1'
        self.device.native.config = Mock(return_value=[{}])

        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with([command])

    def test_config_list(self):
        commands = ['interface Eth1/2', 'no shutdown']
        self.device.native.config = Mock(return_value=[{}, {}])

        result = self.device.config_list(commands)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with(commands)

    def test_show(self):
        command = 'show ip arp'
        return_value = [{'command': 'show ip arp',
                         'result': {
                              u'dynamicEntries': 1,
                              u'notLearnedEntries': 0, u'totalEntries': 1,
                              u'ipV4Neighbors': [{
                                  u'hwAddress': u'2cc2.60ff.0011',
                                  u'interface': u'Management1',
                                  u'age': 0,
                                  u'address': u'10.0.0.2'}],
                              u'staticEntries': 0},
                              'encoding': 'json'}]

        self.device.native.enable = Mock(return_value=return_value)

        result = self.device.show(command)

        self.assertEquals(result, {
                              u'dynamicEntries': 1,
                              u'notLearnedEntries': 0, u'totalEntries': 1,
                              u'ipV4Neighbors': [{
                                  u'hwAddress': u'2cc2.60ff.0011',
                                  u'interface': u'Management1',
                                  u'age': 0,
                                  u'address': u'10.0.0.2'}],
                              u'staticEntries': 0})
        self.device.native.enable.assert_called_with([command], encoding='json')

    def test_show_raw_text(self):
        command = 'show hostname'
        return_value = [{'command': 'show hostname', 'result': {u'output': u'Hostname: spine1\nFQDN:     spine1.ntc.com\n'}, 'encoding': 'text'}]
        self.device.native.enable = Mock(return_value=return_value)

        result = self.device.show(command, raw_text=True)

        self.assertEquals(result, u'Hostname: spine1\nFQDN:     spine1.ntc.com\n')
        self.device.native.enable.assert_called_with([command], encoding='text')

    def test_show_list(self):
        commands = ['show hostname', 'show clock']
        return_value = [{'command': 'show hostname',
                         'result': {
                             u'hostname': u'spine1',
                             u'fqdn': u'spine1.ntc.com'},
                             'encoding': 'json'},
                        {'command': 'show clock',
                         'result': {
                             u'output': u'Thu Dec 10 22:17:10 2015\nTimezone: UTC\nClock source: local\n'},
                             'encoding': 'text'}]

        self.device.native.enable = Mock(return_value=return_value)

        result = self.device.show_list(commands)

        self.assertEquals(result, [{
                                     u'hostname': u'spine1',
                                     u'fqdn': u'spine1.ntc.com',
                                  },
                                  {
                                     u'output': u'Thu Dec 10 22:17:10 2015\nTimezone: UTC\nClock source: local\n',
                                  }])
        self.device.native.enable.assert_called_with(commands, encoding='json')
