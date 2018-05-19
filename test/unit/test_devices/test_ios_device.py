import unittest
import mock
import os

from .device_mocks.ios import send_command, send_command_expect
from pyntc.devices.base_device import RollbackError
from pyntc.devices.ios_device import IOSDevice, FileTransferError, IOS_SSH_DEVICE_TYPE
from pyntc.errors import CommandError, CommandListError


class TestIOSDevice(unittest.TestCase):

    @mock.patch.object(IOSDevice, 'open')
    @mock.patch.object(IOSDevice, 'close')
    @mock.patch('netmiko.cisco.cisco_ios.CiscoIosSSH', autospec=True)
    def setUp(self, mock_miko, mock_close, mock_open):
        self.device = IOSDevice('host', 'user', 'pass')

        mock_miko.send_command.side_effect = send_command
        mock_miko.send_command_expect.side_effect = send_command_expect
        self.device.native = mock_miko

    def test_config(self):
        command = 'interface fastEthernet 0/1'
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.send_command.assert_called_with(command)

    def test_bad_config(self):
        command = 'asdf poknw'

        with self.assertRaisesRegexp(CommandError, command):
            self.device.config(command)

    def test_config_list(self):
        commands = ['interface fastEthernet 0/1', 'no shutdown']
        result = self.device.config_list(commands)

        self.assertIsNone(result)

        calls = list(mock.call(x) for x in commands)
        self.device.native.send_command.assert_has_calls(calls)

    def test_bad_config_list(self):
        commands = ['interface fastEthernet 0/1', 'apons']

        with self.assertRaisesRegexp(CommandListError, commands[1]):
            self.device.config_list(commands)

    def test_show(self):
        command = 'show ip arp'
        result = self.device.show(command)

        self.assertIsInstance(result, str)
        self.assertIn('Protocol', result)
        self.assertIn('Address', result)

        self.device.native.send_command.assert_called_with(command)

    def test_bad_show(self):
        command = 'show microsoft'
        with self.assertRaises(CommandError):
            self.device.show(command)

    def test_show_list(self):
        commands = ['show version', 'show clock']

        result = self.device.show_list(commands)
        self.assertIsInstance(result, list)

        self.assertIn('uptime is', result[0])
        self.assertIn('UTC', result[1])

        calls = list(mock.call(x) for x in commands)
        self.device.native.send_command.assert_has_calls(calls)

    def test_bad_show_list(self):
        commands = ['show badcommand', 'show clock']
        with self.assertRaisesRegexp(CommandListError, 'show badcommand'):
            self.device.show_list(commands)

    def test_save(self):
        result = self.device.save()
        self.assertTrue(result)
        self.device.native.send_command.assert_any_call('copy running-config startup-config')

    @mock.patch('pyntc.devices.ios_device.FileTransfer', autospec=True)
    def test_file_copy_remote_exists(self, mock_ft):
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists('source_file')

        self.assertTrue(result)

    @mock.patch('pyntc.devices.ios_device.FileTransfer', autospec=True)
    def test_file_copy_remote_exists_bad_md5(self, mock_ft):
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = False

        result = self.device.file_copy_remote_exists('source_file')

        self.assertFalse(result)

    @mock.patch('pyntc.devices.ios_device.FileTransfer', autospec=True)
    def test_file_copy_remote_exists_not(self, mock_ft):
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists('source_file')

        self.assertFalse(result)

    @mock.patch('pyntc.devices.ios_device.FileTransfer', autospec=True)
    def test_file_copy(self, mock_ft):
        mock_ft_instance = mock_ft.return_value

        self.device.file_copy('path/to/source_file')

        mock_ft.assert_called_with(self.device.native, 'path/to/source_file', 'source_file', file_system='flash:')
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch('pyntc.devices.ios_device.FileTransfer', autospec=True)
    def test_file_copy_different_dest(self, mock_ft):
        mock_ft_instance = mock_ft.return_value

        self.device.file_copy('source_file', 'dest_file')

        mock_ft.assert_called_with(self.device.native, 'source_file', 'dest_file', file_system='flash:')
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch('pyntc.devices.ios_device.FileTransfer', autospec=True)
    def test_file_copy_fail(self, mock_ft):
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = Exception

        with self.assertRaises(FileTransferError):
            self.device.file_copy('source_file')

    def test_reboot(self):
        self.device.reboot(confirm=True)
        self.device.native.send_command.assert_any_call('reload')

    def test_reboot_with_timer(self):
        self.device.reboot(confirm=True, timer=5)
        self.device.native.send_command.assert_any_call('reload in 5')

    def test_reboot_no_confirm(self):
        self.device.reboot()
        assert not self.device.native.send_command.called

    def test_get_boot_options(self):
        boot_options = self.device.get_boot_options()
        self.assertEqual(boot_options, {'sys': 'other_image'})

    @mock.patch.object(IOSDevice, '_is_catalyst', return_value=True)
    def test_get_boot_options_catalyst(self, mock_is_cat):
        boot_options = self.device.get_boot_options()
        self.assertEqual(boot_options, {'sys': 'c3560-advipservicesk9-mz.122-44.SE'})

    def test_set_boot_options(self):
        self.device.set_boot_options('new_image.swi')
        self.device.native.send_command.assert_called_with('boot system flash new_image.swi')

    @mock.patch.object(IOSDevice, '_is_catalyst', return_value=True)
    def test_set_boot_options(self, mock_is_cat):
        self.device.set_boot_options('new_image.swi')
        self.device.native.send_command.assert_called_with('boot system flash:/new_image.swi')

    def test_backup_running_config(self):
        filename = 'local_running_config'
        self.device.backup_running_config(filename)

        with open(filename, 'r') as f:
            contents = f.read()

        self.assertEqual(contents, self.device.running_config)
        os.remove(filename)

    def test_rollback(self):
        self.device.rollback('good_checkpoint')
        self.device.native.send_command.assert_called_with('configure replace flash:good_checkpoint force')

    def test_bad_rollback(self):
        with self.assertRaises(RollbackError):
            self.device.rollback('bad_checkpoint')

    def test_checkpiont(self):
        self.device.checkpoint('good_checkpoint')
        self.device.native.send_command.assert_any_call('copy running-config good_checkpoint')

    def test_facts(self):
        facts = self.device.facts
        expected = {
            'uptime': 413940,
            'vendor': 'cisco',
            'uptime_string': '04:18:59:00',
            'interfaces': ['FastEthernet0/0', 'FastEthernet0/1'],
            'hostname': 'rtr2811',
            IOS_SSH_DEVICE_TYPE: {'config_register': '0x2102'},
            'fqdn': 'N/A',
            'os_version': '15.1(3)T4',
            'serial_number': '',
            'model': '2811',
            'vlans': []
        }
        self.assertEqual(facts, expected)


        self.device.native.send_command.reset_mock()
        facts = self.device.facts
        self.assertEqual(facts, expected)

        self.device.native.send_command.assert_not_called()

    def test_running_config(self):
        expected = self.device.show('show running-config')
        self.assertEqual(self.device.running_config, expected)

    def test_starting_config(self):
        expected = self.device.show('show startup-config')
        self.assertEqual(self.device.startup_config, expected)


if __name__ == '__main__':
    unittest.main()
