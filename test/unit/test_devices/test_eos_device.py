import unittest
import mock
import os

from .device_mocks.eos import enable, config
from .device_mocks.eos import send_command, send_command_expect
from pyntc.devices import EOSDevice
from pyntc.devices.base_device import RollbackError, RebootTimerError
from pyntc.devices.eos_device import FileTransferError
from pyntc.devices.system_features.vlans.eos_vlans import EOSVlans
from pyntc.errors import CommandError, CommandListError


class TestEOSDevice(unittest.TestCase):
    @mock.patch("pyeapi.client.Node", autospec=True)
    def setUp(self, mock_node):
        self.device = EOSDevice("host", "user", "pass")
        self.maxDiff = None

        mock_node.enable.side_effect = enable
        mock_node.config.side_effect = config
        self.device.native = mock_node

    def tearDown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()

    def test_config(self):
        command = "interface Eth1"
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with([command])

    def test_bad_config(self):
        command = "asdf poknw"

        with self.assertRaisesRegex(CommandError, command):
            self.device.config(command)

    def test_config_list(self):
        commands = ["interface Eth1", "no shutdown"]
        result = self.device.config_list(commands)

        self.assertIsNone(result)
        self.device.native.config.assert_called_with(commands)

    def test_bad_config_list(self):
        commands = ["interface Eth1", "apons"]

        with self.assertRaisesRegex(CommandListError, commands[1]):
            self.device.config_list(commands)

    def test_show(self):
        command = "show ip arp"
        result = self.device.show(command)

        self.assertIsInstance(result, dict)
        self.assertNotIn("command", result)
        self.assertIn("dynamicEntries", result)

        self.device.native.enable.assert_called_with([command], encoding="json")

    def test_bad_show(self):
        command = "show microsoft"
        with self.assertRaises(CommandError):
            self.device.show(command)

    def test_show_raw_text(self):
        command = "show hostname"
        result = self.device.show(command, raw_text=True)

        self.assertIsInstance(result, str)
        self.assertEqual(result, "Hostname: spine1\nFQDN:     spine1.ntc.com\n")
        self.device.native.enable.assert_called_with([command], encoding="text")

    def test_show_list(self):
        commands = ["show hostname", "show clock"]

        result = self.device.show_list(commands)
        self.assertIsInstance(result, list)

        self.assertIn("hostname", result[0])
        self.assertIn("fqdn", result[0])
        self.assertIn("output", result[1])

        self.device.native.enable.assert_called_with(commands, encoding="json")

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        with self.assertRaisesRegex(CommandListError, "show badcommand"):
            self.device.show_list(commands)

    def test_save(self):
        result = self.device.save()
        self.assertTrue(result)
        self.device.native.enable.assert_called_with(["copy running-config startup-config"], encoding="json")

    @mock.patch("pyeapi.client.Node", autospec=True)
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def setup_test_file_copy_remote_exists(self, test_file_copy_remote_exists, mock_ssh, mock_node):
        self.device = EOSDevice("host", "user", "pass")
        self.maxDiff = None

        mock_node.enable.side_effect = enable
        mock_node.config.side_effect = config
        self.device.native = mock_node
        mock_ssh.send_command_timing.side_effect = send_command
        mock_ssh.send_command_expect.side_effect = send_command_expect
        self.device.native_ssh = mock_ssh

    def teardown_test_file_copy_remote_exists(self, test_file_copy_remote_exists):
        self.device.native.reset_mock()
        self.device.native_ssh.reset_mock()

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_remote_exists(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertTrue(result)

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_remote_exists_bad_md5(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = False

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_remote_not_exist(self, mock_open, mock_close, mock_ssh, mock_ft):

        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(self.device.native_ssh, "path/to/source_file", "source_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_different_dest(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("source_file", "dest_file")

        mock_ft.assert_called_with(self.device.native_ssh, "source_file", "dest_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.eos_device.FileTransfer", autospec=True)
    @mock.patch.object(EOSDevice, "open")
    @mock.patch.object(EOSDevice, "close")
    @mock.patch("netmiko.arista.arista.AristaSSH", autospec=True)
    def test_file_copy_fail(self, mock_open, mock_close, mock_ssh, mock_ft):
        self.device.native_ssh = mock_open
        self.device.native_ssh.send_command_timing.side_effect = None
        self.device.native_ssh.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = Exception
        mock_ft_instance.check_file_exists.return_value = False

        with self.assertRaises(FileTransferError):
            self.device.file_copy("source_file")

    def test_reboot(self):
        self.device.reboot(confirm=True)
        self.device.native.enable.assert_called_with(["reload now"], encoding="json")

    def test_reboot_no_confirm(self):
        self.device.reboot()
        assert not self.device.native.enable.called

    def test_reboot_with_timer(self):
        with self.assertRaises(RebootTimerError):
            self.device.reboot(confirm=True, timer=3)

    def test_boot_options(self):
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": "EOS.swi"})

    def test_set_boot_options(self):
        results = [
            [{"result": {"output": "flash:"}}],
            [{"result": {"output": "new_image.swi"}}],
            [{"result": {}}],
            [{"result": {"softwareImage": "flash:new_image.swi"}}],
        ]
        calls = [
            mock.call(["dir"], encoding="text"),
            mock.call(["dir flash:"], encoding="text"),
            mock.call(["install source flash:new_image.swi"], encoding="json"),
            mock.call(["show boot-config"], encoding="json"),
        ]
        self.device.native.enable.side_effect = results
        self.device.set_boot_options("new_image.swi")
        self.device.native.enable.assert_has_calls(calls)

    def test_backup_running_config(self):
        filename = "local_running_config"
        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        self.assertEqual(contents, self.device.running_config)
        os.remove(filename)

    def test_rollback(self):
        self.device.rollback("good_checkpoint")
        self.device.native.enable.assert_called_with(["configure replace good_checkpoint force"], encoding="json")

    def test_bad_rollback(self):
        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpiont(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.enable.assert_called_with(["copy running-config good_checkpoint"], encoding="json")

    @mock.patch.object(EOSVlans, "get_list", autospec=True)
    def test_facts(self, mock_vlan_list):
        mock_vlan_list.return_value = ["1", "2", "10"]
        facts = self.device.facts
        self.assertIsInstance(facts["uptime"], int)
        self.assertIsInstance(facts["uptime_string"], str)

        del facts["uptime"]
        del facts["uptime_string"]

        expected = {
            "vendor": "arista",
            "os_version": "4.14.7M-2384414.4147M",
            "interfaces": [
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
                "Ethernet4",
                "Ethernet5",
                "Ethernet6",
                "Ethernet7",
                "Ethernet8",
                "Management1",
            ],
            "hostname": "eos-spine1",
            "fqdn": "eos-spine1.ntc.com",
            "serial_number": "",
            "model": "vEOS",
            "vlans": ["1", "2", "10"],
        }
        self.assertEqual(facts, expected)

        self.device.native.enable.reset_mock()
        facts = self.device.facts
        self.assertEqual(facts, expected)
        self.device.native.enable.assert_not_called()

    def test_running_config(self):
        expected = self.device.show("show running-config", raw_text=True)
        self.assertEqual(self.device.running_config, expected)

    def test_starting_config(self):
        expected = self.device.show("show startup-config", raw_text=True)
        self.assertEqual(self.device.startup_config, expected)


if __name__ == "__main__":
    unittest.main()


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_no_transport(mock_eos_connect):
    EOSDevice("host", "username", "password")
    mock_eos_connect.assert_called_with(host="host", username="username", password="password", transport="http")


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_https_transport(mock_eos_connect):
    EOSDevice("host", "username", "password", transport="https")
    mock_eos_connect.assert_called_with(host="host", username="username", password="password", transport="https")


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_pass_port(mock_eos_connect):
    EOSDevice("host", "username", "password", port=8080)
    mock_eos_connect.assert_called_with(
        host="host", username="username", password="password", transport="http", port=8080
    )


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_pass_timeout(mock_eos_connect):
    EOSDevice("host", "username", "password", timeout=30)
    mock_eos_connect.assert_called_with(
        host="host", username="username", password="password", transport="http", timeout=30
    )


@mock.patch("pyntc.devices.eos_device.eos_connect")
def test_init_pass_port_and_timeout(mock_eos_connect):
    EOSDevice("host", "username", "password", port=8080, timeout=30)
    mock_eos_connect.assert_called_with(
        host="host", username="username", password="password", transport="http", port=8080, timeout=30
    )
