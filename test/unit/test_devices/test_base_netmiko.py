from unittest import mock

import pytest

from pyntc.devices import base_netmiko as netmiko_module
from pyntc.devices.base_netmiko import BaseNetmikoDevice
from pyntc.devices import AIREOSDevice, ASADevice, IOSDevice


NETMIKO_IMPLEMENTATIONS = (AIREOSDevice, ASADevice, IOSDevice)
NETMIKO_IMPLEMENTATION_PLATFORMS = ("aireos", "asa", "ios")


def test_init():
    dev = BaseNetmikoDevice("host1", "user", "pass", "cisco_ios_ssh")
    assert dev.native is None
    assert dev.secret == ""
    assert dev.port == 22
    assert dev._connected is False


def test_check_command_output_has_error(netmiko_device):
    command_fails = netmiko_device._check_command_output_has_error("valid output")
    assert command_fails is False


@pytest.mark.parametrize(
    "output",
    ("Incorrect usage: invalid output", "Error: invalid output", r"% Invalid command"),
    ids=("incorrect", "error", "percent"),
)
def test_check_command_output_has_error_error(output, netmiko_device):
    command_fails = netmiko_device._check_command_output_has_error(output)
    assert command_fails is True


@mock.patch.object(BaseNetmikoDevice, "_check_command_output_has_error", return_value=False)
def test_send_commands(mock_command_has_error, netmiko_method, netmiko_command):
    commands = ["valid command", "valid command also"]
    responses = ["valid", "valid also"]
    device = netmiko_command(netmiko_method, responses)
    native_method = getattr(device.native, netmiko_method)
    actual = device._send_commands(native_method, commands, {})
    assert actual == responses
    native_method.assert_has_calls((mock.call(command) for command in commands))
    mock_command_has_error.assert_has_calls((mock.call(response) for response in responses))


@mock.patch.object(BaseNetmikoDevice, "_check_command_output_has_error", side_effect=[False, True])
def test_send_commands_error(mock_command_has_error, netmiko_method, netmiko_command):
    commands = ["valid command", "invalid command", "valid command also"]
    responses = ["valid", "Error: invalid command"]
    device = netmiko_command(netmiko_method, responses)
    native_method = getattr(device.native, netmiko_method)
    with pytest.raises(netmiko_module.CommandError) as err:
        device._send_commands(native_method, commands, {})
    assert err.value.command == commands[1]
    assert err.value.cli_error_msg == responses[1]
    assert err.value.commands == commands[:2]
    native_method.assert_has_calls((mock.call(command) for command in commands[:2]))
    assert mock.call(commands[2]) not in native_method.mock_calls
    mock_command_has_error.assert_has_calls((mock.call(response) for response in responses))


def test_send_commands_netmiko_args(netmiko_method, netmiko_command):
    commands = ["valid command"]
    responses = ["valid"]
    device = netmiko_command(netmiko_method, responses)
    native_method = getattr(device.native, netmiko_method)
    netmiko_args = {"delay_factor": 5}
    actual = device._send_commands(native_method, commands, netmiko_args)
    assert actual == responses
    native_method.assert_called_with(commands[0], **netmiko_args)


def test_send_commands_netmiko_args_type_error(netmiko_method, netmiko_command):
    commands = ["valid command"]
    device = netmiko_command(netmiko_method, [])
    native_method = getattr(device.native, netmiko_method)
    netmiko_args = {"invalid_netmiko_arg": 1}
    with pytest.raises(TypeError) as err:
        device._send_commands(native_method, commands, netmiko_args)
    assert err.value.args[0].startswith("Netmiko Driver's")


def test_connected_getter(netmiko_device):
    netmiko_device._connected = False
    assert netmiko_device.connected is False
    netmiko_device._connected = True
    assert netmiko_device.connected is True


def test_connected_setter(netmiko_device):
    netmiko_device._connected = False
    netmiko_device.connected = True
    assert netmiko_device._connected is True
    netmiko_device.connected = False
    assert netmiko_device.connected is False


def test_show_arg_string(netmiko_send_commands):
    command = "valid command"
    response = "valid"
    device = netmiko_send_commands([[response]])
    actual = device.show(command)
    assert actual == response
    device._send_commands.assert_called_with(device.native.send_command, [command], {})


def test_show_arg_list(netmiko_send_commands):
    commands = ["valid command", "valid command also"]
    responses = ["valid", "valid also"]
    device = netmiko_send_commands([responses])
    actual = device.show(commands)
    assert actual == responses
    device._send_commands.assert_called_with(device.native.send_command, commands, {})


def test_show_arg_string_netmiko_args(netmiko_send_commands):
    command = "valid command"
    response = "valid"
    netmiko_args = {"delay_factor": 5}
    device = netmiko_send_commands([[response]])
    actual = device.show(command, **netmiko_args)
    assert actual == response
    device._send_commands.assert_called_with(device.native.send_command, [command], netmiko_args)


def test_show_arg_list_netmiko_args(netmiko_send_commands):
    commands = ["valid command", "valid command also"]
    responses = ["valid", "valid also"]
    netmiko_args = {"delay_factor": 5}
    device = netmiko_send_commands([responses])
    actual = device.show(commands, **netmiko_args)
    assert actual == responses
    device._send_commands.assert_called_with(device.native.send_command, commands, netmiko_args)


def test_show_arg_string_netmiko_args_type_error(netmiko_send_commands):
    command = "valid command"
    response = TypeError()
    netmiko_args = {"invalid_netmiko_arg": 5}
    device = netmiko_send_commands([response])
    with pytest.raises(TypeError):
        device.show(command, **netmiko_args)


def test_show_arg_list_netmiko_args_type_error(netmiko_send_commands):
    commands = ["valid command"]
    responses = [TypeError()]
    netmiko_args = {"invalid_netmiko_arg": 5}
    device = netmiko_send_commands(responses)
    with pytest.raises(TypeError):
        device.show(commands, **netmiko_args)


def test_show_arg_string_error(netmiko_send_commands):
    command = "invalid command"
    response = netmiko_module.CommandError(command, "Error: invalid command", [command])
    device = netmiko_send_commands([response])
    with pytest.raises(netmiko_module.CommandError) as err:
        device.show(command)
    assert err.value == response


def test_show_arg_list_error(netmiko_send_commands):
    commands = ["invalid command"]
    responses = [netmiko_module.CommandListError(commands, commands[0], "Error: invalid command")]
    device = netmiko_send_commands(responses)
    with pytest.raises(netmiko_module.CommandListError) as err:
        device.show(commands)
    assert err.value == responses[0]


def test_show_list(netmiko_show):
    commands = ["valid command"]
    responses = ["valid"]
    device = netmiko_show([responses])
    actual = device.show_list(commands)
    assert actual == responses
    device.show.assert_called_with(commands)


def test_show_list_netmiko_args(netmiko_show):
    commands = ["valid command"]
    responses = ["valid"]
    netmiko_args = {"global_delay_factor": 5}
    device = netmiko_show([responses])
    actual = device.show_list(commands, **netmiko_args)
    assert actual == responses
    device.show.assert_called_with(commands, **netmiko_args)


# Test implementations of base class


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_check_command_output_has_error_implementations(netmiko_base_implementation):
    device = netmiko_base_implementation()
    command_fails = device._check_command_output_has_error("valid output")
    assert command_fails is False


@pytest.mark.parametrize(
    "output",
    ("Incorrect usage: invalid output", "Error: invalid output", r"% Invalid command"),
    ids=("incorrect", "error", "%"),
)
@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_check_command_output_has_error_error_implementations(netmiko_base_implementation, output):
    device = netmiko_base_implementation()
    command_fails = device._check_command_output_has_error(output)
    assert command_fails is True


@mock.patch.object(BaseNetmikoDevice, "_check_command_output_has_error", return_value=False)
@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_send_commands_implementations(mock_command_has_error, netmiko_base_implementation, netmiko_method):
    commands = ["valid command", "valid command also"]
    responses = ["valid", "valid also"]
    device = netmiko_base_implementation()
    native_method = getattr(device.native, netmiko_method)
    native_method.side_effect = responses
    actual = device._send_commands(native_method, commands, {})
    assert actual == responses
    native_method.assert_has_calls((mock.call(command) for command in commands))
    mock_command_has_error.assert_has_calls((mock.call(response) for response in responses))


@mock.patch.object(BaseNetmikoDevice, "_check_command_output_has_error", side_effect=[False, True])
@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_send_commands_error_implementations(mock_command_has_error, netmiko_base_implementation, netmiko_method):
    commands = ["valid command", "invalid command", "valid command also"]
    responses = ["valid", "Error: invalid command"]
    device = netmiko_base_implementation()
    native_method = getattr(device.native, netmiko_method)
    native_method.side_effect = responses
    with pytest.raises(netmiko_module.CommandError) as err:
        device._send_commands(native_method, commands, {})
    assert err.value.command == commands[1]
    assert err.value.cli_error_msg == responses[1]
    assert err.value.commands == commands[:2]
    native_method.assert_has_calls((mock.call(command) for command in commands[:2]))
    assert mock.call(commands[2]) not in native_method.mock_calls
    mock_command_has_error.assert_has_calls((mock.call(response) for response in responses))


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_send_commands_netmiko_args_implementations(netmiko_method, netmiko_base_implementation):
    commands = ["valid command"]
    responses = ["valid"]
    device = netmiko_base_implementation()
    native_method = getattr(device.native, netmiko_method)
    native_method.side_effect = responses
    netmiko_args = {"delay_factor": 5}
    actual = device._send_commands(native_method, commands, netmiko_args)
    assert actual == responses
    native_method.assert_called_with(commands[0], **netmiko_args)


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_connected_getter_implementations(netmiko_base_implementation):
    device = netmiko_base_implementation()
    device._connected = False
    assert device.connected is False
    device._connected = True
    assert device.connected is True


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_connected_setter_implementations(netmiko_base_implementation):
    device = netmiko_base_implementation()
    device._connected = False
    device.connected = True
    assert device.connected is True
    device.connected = False
    assert device.connected is False


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_string_implementations(netmiko_base_implementation):
    command = "valid command"
    response = "valid"
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=[[response]])
    actual = device.show(command)
    assert actual == response
    device._send_commands.assert_called_with(device.native.send_command, [command], {})


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_list_implementations(netmiko_base_implementation):
    commands = ["valid command", "valid command also"]
    responses = ["valid", "valid also"]
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=[responses])
    actual = device.show(commands)
    assert actual == responses
    device._send_commands.assert_called_with(device.native.send_command, commands, {})


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_string_netmiko_args_implementations(netmiko_base_implementation):
    command = "valid command"
    response = "valid"
    netmiko_args = {"delay_factor": 5}
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=[[response]])
    actual = device.show(command, **netmiko_args)
    assert actual == response
    device._send_commands.assert_called_with(device.native.send_command, [command], netmiko_args)


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_list_netmiko_args_implementations(netmiko_base_implementation):
    commands = ["valid command", "valid command also"]
    responses = ["valid", "valid also"]
    netmiko_args = {"delay_factor": 5}
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=[responses])
    actual = device.show(commands, **netmiko_args)
    assert actual == responses
    device._send_commands.assert_called_with(device.native.send_command, commands, netmiko_args)


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_string_netmiko_args_type_error_implementations(netmiko_base_implementation):
    command = "valid command"
    response = TypeError()
    netmiko_args = {"invalid_netmiko_arg": 5}
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=[response])
    with pytest.raises(TypeError):
        device.show(command, **netmiko_args)


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_list_netmiko_args_type_error_implementations(netmiko_base_implementation):
    commands = ["valid command"]
    responses = [TypeError()]
    netmiko_args = {"invalid_netmiko_arg": 5}
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=responses)
    with pytest.raises(TypeError):
        device.show(commands, **netmiko_args)


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_string_error_implementations(netmiko_base_implementation):
    command = "invalid command"
    response = netmiko_module.CommandError(command, "Error: invalid command", [command])
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=[response])
    with pytest.raises(netmiko_module.CommandError) as err:
        device.show(command)
    assert err.value == response


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_arg_list_error_implementations(netmiko_base_implementation):
    commands = ["invalid command"]
    responses = [netmiko_module.CommandListError(commands, commands[0], "Error: invalid command")]
    device = netmiko_base_implementation()
    device._send_commands = mock.Mock(device._send_commands, side_effect=responses)
    with pytest.raises(netmiko_module.CommandListError) as err:
        device.show(commands)
    assert err.value == responses[0]


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_list_implementations(netmiko_base_implementation, mock_implementation_show):
    commands = ["valid command"]
    responses = ["valid"]
    device = mock_implementation_show(netmiko_base_implementation, [responses])
    actual = device.show_list(commands)
    assert actual == responses
    device.show.assert_called_with(commands)


@pytest.mark.parametrize(
    "netmiko_base_implementation", NETMIKO_IMPLEMENTATIONS, indirect=True, ids=NETMIKO_IMPLEMENTATION_PLATFORMS
)
def test_show_list_netmiko_args_implementations(netmiko_base_implementation, mock_implementation_show):
    commands = ["valid command"]
    responses = ["valid"]
    netmiko_args = {"global_delay_factor": 5}
    device = mock_implementation_show(netmiko_base_implementation, [responses])
    actual = device.show_list(commands, **netmiko_args)
    assert actual == responses
    device.show.assert_called_with(commands, **netmiko_args)
