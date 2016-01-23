import unittest
import mock

from device_mocks.eos import enable, config

from pyntc.devices import EOSDevice


class TestEOSDevice(unittest.TestCase):

    @mock.patch('pyeapi.client.Node', autospec=True)
    def setUp(self, mock_node):
        self.device = EOSDevice('host', 'user', 'pass')

        mock_node.enable.side_effect = enable
        mock_node.config.side_effect = config
        self.device.native = mock_node

    def test_config(self):
        command = 'interface Eth1'
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with([command])

    def test_config_list(self):
        commands = ['interface Eth1', 'no shutdown']
        result = self.device.config_list(commands)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with(commands)

    def test_show(self):
        command = 'show ip arp'
        result = self.device.show(command)

        self.assertIsInstance(result, dict)
        self.assertNotIn('command', result)
        self.assertIn('dynamicEntries', result)

        self.device.native.enable.assert_called_with(
            [command], encoding='json')

    def test_show_raw_text(self):
        command = 'show hostname'
        result = self.device.show(command, raw_text=True)

        self.assertIsInstance(result, str)
        self.assertEquals(result,
                          'Hostname: spine1\nFQDN:     spine1.ntc.com\n')
        self.device.native.enable.assert_called_with([command], encoding='text')

    def test_show_list(self):
        commands = ['show hostname', 'show clock']

        result = self.device.show_list(commands)
        self.assertIsInstance(result, list)

        self.assertIn('hostname', result[0])
        self.assertIn('fqdn', result[0])
        self.assertIn('output', result[1])

        self.device.native.enable.assert_called_with(commands, encoding='json')

if __name__ == '__main__':
    unittest.main()
