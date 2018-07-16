import os
import json
from pynxos.errors import CLIError

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


def show(command, raw_text=False):
    """

    TODO: Add docstring
    """
    command = command.replace(' ', '_')
    command = command.replace('/', '_')

    if raw_text:
        path = os.path.join(CURRENT_DIR, 'show_raw', command)
    else:
        path = os.path.join(CURRENT_DIR, 'show', command)

    if not os.path.isfile(path):
        raise CLIError(command, 'Invalid command.')

    with open(path, 'r') as f:
        response = f.read()

    if raw_text:
        return response
    else:
        return json.loads(response)


def show_list(commands, raw_text=False):
    """

    TODO: Add docstring
    TODO: Check that no code is passing in extra args and remove raw_text
    """
    responses = []
    for command in commands:
        responses.append(show(command))

    return responses
