import unittest
import mock
import os
import pytest

from tempfile import NamedTemporaryFile

from pyntc.devices import JunosDevice
from pyntc.errors import CommandError, CommandListError

from jnpr.junos.exception import ConfigLoadError


DEVICE_FACTS = {
    "domain": "ntc.com",
    "hostname": "vmx3",
    "ifd_style": "CLASSIC",
    "version_RE0": "15.1F4.15",
    "2RE": False,
    "serialnumber": "VMX9a",
    "fqdn": "vmx3.ntc.com",
    "virtual": True,
    "switch_style": "BRIDGE_DOMAIN",
    "version": "15.1F4.15",
    "master": "RE0",
    "HOME": "/var/home/ntc",
    "model": "VMX",
    "RE0": {
        "status": "OK",
        "last_reboot_reason": "0x200:normal shutdown ",
        "model": "RE-VMX",
        "up_time": "7 minutes, 35 seconds",
        "mastership_state": "master",
    },
    "vc_capable": False,
    "personality": "MX",
}


class TestJnprDevice(unittest.TestCase):
    def setUp(self):
        self.mock_sw = mock.patch("pyntc.devices.jnpr_device.JunosNativeSW", autospec=True)
        self.mock_fs = mock.patch("pyntc.devices.jnpr_device.JunosNativeFS", autospec=True)
        self.mock_config = mock.patch("pyntc.devices.jnpr_device.JunosNativeConfig", autospec=True)
        self.mock_device = mock.patch("pyntc.devices.jnpr_device.JunosNativeDevice", autospec=True)

        self.mock_sw.start()
        self.mock_fs.start()
        self.mock_config.start()
        self.mock_device.start()

        self.device = JunosDevice("host", "user", "pass")
        self.device.native.facts = DEVICE_FACTS

    def tearDown(self):
        self.mock_sw.stop()
        self.mock_fs.stop()
        self.mock_config.stop()
        self.mock_device.stop()

    def test_config_pass_string(self):
        command = "set interfaces lo0"
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.cu.load.assert_called_with(command, format="set")
        self.device.cu.commit.assert_called_with()

    def test_config_pass_list(self):
        commands = ["set interfaces lo0", "set snmp community jason"]
        result = self.device.config(commands)

        self.assertIsNone(result)
        self.device.cu.load.assert_has_calls(mock.call(command, format="set") for command in commands)
        self.device.cu.commit.assert_called_with()

    @mock.patch.object(JunosDevice, "config")
    def test_config_list(self, mock_config):
        commands = ["set interfaces lo0", "set snmp community jason"]

        self.device.config_list(commands, format="set")
        self.device.config.assert_called_with(commands, format="set")

    def test_bad_config_pass_string(self):
        command = "asdf poknw"
        self.device.cu.load.side_effect = ConfigLoadError(command)

        with pytest.raises(CommandError) as err:
            self.device.config(command)
        assert err.value.command == command

    def test_bad_config_pass_list(self):
        commands = ["set interface lo0", "apons"]

        def load_side_effect(*args, **kwargs):
            if args[0] == commands[1]:
                raise ConfigLoadError(args[0])

        self.device.cu.load.side_effect = load_side_effect

        with pytest.raises(CommandListError) as err:
            self.device.config(commands)
        assert err.value.command == commands[1]

    def test_show_pass_string(self):
        command = "show configuration snmp"

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

    def test_show_pass_list(self):
        commands = ["show vlans", "show snmp v3"]

        def cli_side_effect(*args, **kwargs):
            cli_command = args[0]
            if cli_command == commands[0]:
                return "a"
            if cli_command == commands[1]:
                return "b"

        self.device.native.cli.side_effect = cli_side_effect

        result = self.device.show(commands)
        self.assertIsInstance(result, list)

        self.assertEqual("a", result[0])
        self.assertEqual("b", result[1])

        self.device.native.cli.assert_any_call(commands[0], warning=False)
        self.device.native.cli.assert_any_call(commands[1], warning=False)

    def test_bad_show_non_show_pass_string(self):
        command = "configure something"
        response = 'Juniper "show" commands must begin with "show".'
        with pytest.raises(CommandError) as err:
            self.device.show(command)
        assert err.value.command == "configure something"
        assert err.value.cli_error_msg == response

    def test_bad_show_non_show_pass_list(self):
        commands = ["show version", "configure something"]
        response = [
            "valid",
            '\nCommand configure something failed with message: Juniper "show" commands must begin with "show".\nCommand List: \n\tshow version\n\tconfigure something\n',
        ]
        with pytest.raises(CommandListError) as err:
            self.device.show(commands)
        assert err.value.command == commands[1]
        assert err.value.message == response[1]

    @mock.patch.object(JunosDevice, "show")
    def test_show_list(self, mock_show):
        commands = ["show vlans", "show snmp v3"]

        self.device.show_list(commands)
        self.device.show.assert_called_with(commands)

    @mock.patch("pyntc.devices.jnpr_device.SCP", autospec=True)
    def test_save(self, mock_scp):
        self.device.show = mock.MagicMock()
        self.device.show.return_value = b"file contents"

        result = self.device.save(filename="saved_config")

        self.assertTrue(result)
        self.device.show.assert_called_with("show config")

    def test_file_copy_remote_exists(self):
        temp_file = NamedTemporaryFile()
        temp_file.write(b"file contents")
        temp_file.flush()

        local_checksum = "4a8ec4fa5f01b4ab1a0ab8cbccb709f0"
        self.device.fs.checksum.return_value = local_checksum

        result = self.device.file_copy_remote_exists(temp_file.name, "dest")

        self.assertTrue(result)
        self.device.fs.checksum.assert_called_with("dest")

    def test_file_copy_remote_exists_failure(self):
        temp_file = NamedTemporaryFile()
        temp_file.write(b"file contents")
        temp_file.flush()

        self.device.fs.checksum.return_value = "deadbeef"

        result = self.device.file_copy_remote_exists(temp_file.name, "dest")

        self.assertFalse(result)
        self.device.fs.checksum.assert_called_with("dest")

    @mock.patch("pyntc.devices.jnpr_device.SCP")
    def test_file_copy(self, mock_scp):
        temp_file = NamedTemporaryFile()
        temp_file.write(b"file contents")
        temp_file.flush()

        local_checksum = "4a8ec4fa5f01b4ab1a0ab8cbccb709f0"
        self.device.fs.checksum.side_effect = ["", local_checksum]
        self.device.file_copy(temp_file.name, "dest")
        mock_scp.assert_called_with(self.device.native)

    def test_reboot(self):
        self.device.reboot()
        self.device.sw.reboot.assert_called_with(in_min=0)

    def test_reboot_timer(self):
        self.device.reboot(timer=2)
        self.device.sw.reboot.assert_called_with(in_min=2)

    @mock.patch("pyntc.devices.jnpr_device.JunosDevice.running_config", new_callable=mock.PropertyMock)
    def test_backup_running_config(self, mock_run):
        filename = "local_running_config"

        fake_contents = "fake contents"
        mock_run.return_value = fake_contents

        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        self.assertEqual(contents, fake_contents)
        os.remove(filename)

    @mock.patch("pyntc.devices.jnpr_device.SCP")
    def test_rollback(self, mock_scp):
        self.device.rollback("good_checkpoint")

        mock_scp.assert_called_with(self.device.native)
        assert self.device.cu.load.called
        assert self.device.cu.commit.called

    @mock.patch("pyntc.devices.jnpr_device.SCP", autospec=True)
    def test_checkpoint(self, mock_scp):
        self.device.show = mock.MagicMock()
        self.device.show.return_value = b"file contents"
        self.device.checkpoint("saved_config")
        self.device.show.assert_called_with("show config")

    def test_uptime(self):
        uptime = self.device.uptime
        assert uptime == 455

    def test_uptime_string(self):
        uptime_string = self.device.uptime_string
        assert uptime_string == "00:00:07:35"

    def test_vendor(self):
        vendor = self.device.vendor
        assert vendor == "juniper"

    def test_os_version(self):
        os_version = self.device.os_version
        assert os_version == "15.1F4.15"

    def test_interfaces(self):
        self.device._get_interfaces = mock.MagicMock()
        self.device._get_interfaces.return_value = ["lo0", "ge0"]
        interfaces = self.device.interfaces
        assert interfaces == ["lo0", "ge0"]

    def test_hostname(self):
        hostname = self.device.hostname
        assert hostname == "vmx3"

    def test_fqdn(self):
        fqdn = self.device.fqdn
        assert fqdn == "vmx3.ntc.com"

    def test_serial_number(self):
        serial_number = self.device.serial_number
        assert serial_number == "VMX9a"

    def test_model(self):
        model = self.device.model
        assert model == "VMX"

    def test_running_config(self):
        self.device.show = mock.MagicMock()
        expected = "running config"
        self.device.show.return_value = expected

        result = self.device.running_config
        self.assertEqual(result, expected)

    def test_starting_config(self):
        self.device.show = mock.MagicMock()
        expected = "running config"
        self.device.show.return_value = expected

        result = self.device.startup_config
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
