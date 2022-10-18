import os
import json
from pyeapi.eapilib import CommandError as EOSCommandError
import re

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


def enable(commands, encoding="json"):
    responses = []
    executed_commands = []
    for command in commands:
        command = command.replace(" ", "_")
        path = os.path.join(CURRENT_DIR, "enable" + "_" + encoding, command)

        executed_commands.append(command)
        if not os.path.isfile(path):
            raise EOSCommandError(1002, "%s failed" % command, commands=executed_commands)

        with open(path, "r") as f:
            response = f.read()

        responses.append(response)

    response_string = ",".join(responses)
    response_string = "[" + response_string + "]"

    return json.loads(response_string)


def config(commands):
    original_command_is_str: bool = isinstance(commands, str)

    if original_command_is_str:
        commands = [commands]  # type: ignore [list-item]

    responses = []
    executed_commands = []
    for command in commands:
        command = command.replace(" ", "_")
        path = os.path.join(CURRENT_DIR, "config", command)

        executed_commands.append(command)
        if not os.path.isfile(path):
            raise EOSCommandError(1002, "%s failed" % command, commands=executed_commands)

        responses.append({})

    return responses


def send_command(command, **kwargs):
    """
    TODO: Document me
    """
    orig = command
    command = command.replace(" ", "_")
    command = command.replace("/", "_")

    if command == "\n":
        command = "return"

    path = os.path.join(CURRENT_DIR, "send_command", command)

    if not os.path.isfile(path):
        return f"% Error: Cannot find mock: {orig}"

    with open(path, "r") as f:
        response = f.read()

    return response


def send_command_expect(command, expect_string=None, **kwargs):
    response = send_command(command)

    if expect_string:
        if not re.search(expect_string, response):
            raise IOError("Search pattern never detected.")

    return response
