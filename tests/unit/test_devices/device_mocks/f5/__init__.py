import os
import re

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


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
