import json
import os

from pyntc.devices.pynxos.errors import CLIError

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


def show(command, raw_text=False):
    command = command.replace(" ", "_")
    command = command.replace("/", "_")

    if raw_text:
        path = os.path.join(CURRENT_DIR, "show_raw", command)
    else:
        path = os.path.join(CURRENT_DIR, "show", command)

    if not os.path.isfile(path):
        raise CLIError(command, "Invalid command.")

    with open(path, "r") as f:
        response = f.read()

    if raw_text:
        return response
    else:
        return json.loads(response)


def netmiko_send_command(command, use_textfsm=False, read_timeout=1):
    if isinstance(command, list):
        return [netmiko_send_command(c, use_textfsm=use_textfsm, read_timeout=read_timeout) for c in command]

    command = command.replace(" ", "_")
    command = command.replace("/", "_")

    if use_textfsm:
        path = os.path.join(CURRENT_DIR, "show_netmiko", command)
    else:
        path = os.path.join(CURRENT_DIR, "show_raw", command)

    if not os.path.isfile(path):
        raise CLIError(command, "Invalid command.")

    with open(path, "r") as f:
        response = f.read()

    if not use_textfsm:
        return response
    else:
        return json.loads(response)


def show_list(commands, raw_text=False):
    responses = []
    for command in commands:
        responses.append(show(command))

    return responses
