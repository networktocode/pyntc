import unittest
import mock
import os

from tempfile import NamedTemporaryFile

from pyntc.devices.jnpr_device import JunosDevice
from pyntc.errors import CommandError, CommandListError

from jnpr.junos.exception import ConfigLoadError


class MockType:
    def __init__(self, *args):
        self.mock = mock.Mock()
    def __call__(self, *args):
        return self.mock

class TestJnprDevice(unittest.TestCase):
    __metaclass__ = MockType

    @mock.patch('jnpr.junos.device.Device', autospec=True)
    @mock.patch('jnpr.junos.utils.config', autospec=True)
    @mock.patch('jnpr.junos.utils.fs', autospec=True)
    @mock.patch('jnpr.junos.utils.sw', autospec=True)
    @mock.patch('jnpr.junos.device.Device.open', autospec=True)
    def setUp(self, mock_open, mock_sw, mock_fs, mock_config, mock_native_device):
        self.device = JunosDevice('host', 'user', 'pass')
        self.device.cu = mock_config.return_value
        self.device.fs = mock_fs.return_value
        self.device.sw = mock_sw.return_value
        self.device.native = mock_native_device

    def test_config(self):
        command = 'set interfaces lo0'
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.cu.load.assert_called_with(command, format='set')
        self.device.cu.commit.assert_called_with()

    def test_bad_config(self):
        command = 'asdf poknw'
        self.device.cu.load.side_effect = ConfigLoadError(command)

        with self.assertRaisesRegexp(CommandError, command):
            self.device.config(command)

    def test_config_list(self):
        commands = ['set interfaces lo0', 'set snmp community jason']
        result = self.device.config_list(commands)

        self.assertIsNone(result)

        for command in commands:
            self.device.cu.load.assert_any_call(command, format='set')

        self.device.cu.commit.assert_called_with()

    def test_bad_config_list(self):
        commands = ['set interface lo0', 'apons']

        def load_side_effect(*args, **kwargs):
            if args[0] == commands[1]:
                raise ConfigLoadError(args[0])

        self.device.cu.load.side_effect = load_side_effect

        with self.assertRaisesRegexp(CommandListError, commands[1]):
            self.device.config_list(commands)

    def test_show(self):
        command = 'show configuration snmp'

        expected = """
            community public {
                authorization read-only;
            }
            community networktocode {
                authorization read-only;
            }
        """

        self.device.native.cli.return_value = expected
        result = self.device.show(command)

        self.assertEqual(result, expected)
        self.device.native.cli.assert_called_with(command, warning=False)

    def test_bad_show_non_show(self):
        command = 'configure something'
        with self.assertRaises(CommandError):
            self.device.show(command)

    def test_show_non_raw_text(self):
        command = 'show configuration snmp'

        with self.assertRaises(ValueError):
            self.device.show(command, raw_text=False)

    def test_show_list(self):
        commands = ['show vlans', 'show snmp v3']

        def cli_side_effect(*args, **kwargs):
            cli_command = args[0]
            if cli_command == commands[0]:
                return 'a'
            if cli_command == commands[1]:
                return 'b'

        self.device.native.cli.side_effect = cli_side_effect

        result = self.device.show_list(commands)
        self.assertIsInstance(result, list)

        self.assertEqual('a', result[0])
        self.assertEqual('b', result[1])

        self.device.native.cli.assert_any_call(commands[0], warning=False)
        self.device.native.cli.assert_any_call(commands[1], warning=False)

    @mock.patch('pyntc.devices.jnpr_device.SCP', autospec=True)
    def test_save(self, mock_scp):
        self.device.show = mock.MagicMock()
        self.device.show.return_value = 'file contents'

        result = self.device.save(filename='saved_config')

        self.assertTrue(result)
        self.device.show.assert_called_with('show config')

    def test_file_copy_remote_exists(self):
        temp_file = NamedTemporaryFile()
        temp_file.write('file contents')
        temp_file.flush()

        local_checksum = '4a8ec4fa5f01b4ab1a0ab8cbccb709f0'
        self.device.fs.checksum.return_value = local_checksum

        result = self.device.file_copy_remote_exists(temp_file.name, 'dest')

        self.assertTrue(result)
        self.device.fs.checksum.assert_called_with('dest')

    def test_file_copy_remote_exists_failure(self):
        temp_file = NamedTemporaryFile()
        temp_file.write('file contents')
        temp_file.flush()

        local_checksum = '4a8ec4fa5f01b4ab1a0ab8cbccb709f0'
        self.device.fs.checksum.return_value = 'deadbeef'

        result = self.device.file_copy_remote_exists(temp_file.name, 'dest')

        self.assertFalse(result)
        self.device.fs.checksum.assert_called_with('dest')

    @mock.patch('pyntc.devices.jnpr_device.SCP')
    def test_file_copy(self, mock_scp):
        self.device.file_copy('source', 'dest')
        mock_scp.assert_called_with(self.device.native)

    def test_reboot(self):
        self.device.reboot(confirm=True)
        self.device.sw.reboot.assert_called_with(in_min=0)

    def test_reboot_timer(self):
        self.device.reboot(confirm=True, timer=2)
        self.device.sw.reboot.assert_called_with(in_min=2)

    def test_reboot_no_confirm(self):
        self.device.reboot()
        assert not self.device.sw.reboot.called

    @mock.patch('pyntc.devices.jnpr_device.JunosDevice.running_config', new_callable=mock.PropertyMock)
    def test_backup_running_config(self, mock_run):
        filename = 'local_running_config'

        fake_contents = 'fake contents'
        mock_run.return_value = fake_contents

        self.device.backup_running_config(filename)

        with open(filename, 'r') as f:
            contents = f.read()

        self.assertEqual(contents, fake_contents)
        os.remove(filename)

    @mock.patch('pyntc.devices.jnpr_device.SCP')
    def test_rollback(self, mock_scp):
        self.device.rollback('good_checkpoint')

        mock_scp.assert_called_with(self.device.native)
        assert self.device.cu.load.called
        assert self.device.cu.commit.called

    @mock.patch('pyntc.devices.jnpr_device.SCP', autospec=True)
    def test_checkpoint(self, mock_scp):
        self.device.show = mock.MagicMock()
        self.device.show.return_value = 'file contents'

        result = self.device.checkpoint('saved_config')

        self.device.show.assert_called_with('show config')

    def test_facts(self):
        self.device.native.facts = {
            'domain': 'ntc.com',
            'hostname': 'vmx3',
            'ifd_style': 'CLASSIC',
            'version_RE0': '15.1F4.15',
            '2RE': False,
            'serialnumber': 'VMX9a',
            'fqdn': 'vmx3.ntc.com',
            'virtual': True,
            'switch_style': 'BRIDGE_DOMAIN',
            'version': '15.1F4.15',
            'master': 'RE0',
            'HOME': '/var/home/ntc',
            'model': 'VMX',
            'RE0': {
                'status': 'OK',
                'last_reboot_reason': '0x200:normal shutdown ',
                'model': 'RE-VMX',
                'up_time': '7 minutes, 35 seconds',
                'mastership_state': 'master'},
                'vc_capable': False,
                'personality': 'MX'
            }

        self.device._get_interfaces = mock.MagicMock()
        self.device._get_interfaces.return_value = ['lo0', 'ge0']

        facts = self.device.facts

        expected = {
            'uptime': 455,
            'vendor': 'juniper',
            'os_version': '15.1F4.15',
            'interfaces': ['lo0', 'ge0'],
            'hostname': 'vmx3',
            'fqdn': 'vmx3.ntc.com',
            'uptime_string': '00:00:07:35',
            'serial_number': 'VMX9a',
            'model': 'VMX'
        }

        self.assertEqual(facts, expected)

    def test_running_config(self):
        self.device.show = mock.MagicMock()
        expected = 'running config'
        self.device.show.return_value = expected

        result = self.device.running_config
        self.assertEqual(result, expected)

    def test_starting_config(self):
        self.device.show = mock.MagicMock()
        expected = 'running config'
        self.device.show.return_value = expected

        result = self.device.startup_config
        self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()
