import os
import json
from pynxos.errors import CLIError

CURRNENT_DIR = os.path.dirname(os.path.realpath(__file__))

def show(command, raw_text=False):
    command = command.replace(' ', '_')
    command = command.replace('/', '_')

    if raw_text:
        path = os.path.join(CURRNENT_DIR, 'show_raw', command)
    else:
        path = os.path.join(CURRNENT_DIR, 'show', command)

    if not os.path.isfile(path):
        raise CLIError(command, 'Invalid command.')

    with open(path, 'r') as f:
        response = f.read()

    if raw_text:
        return response
    else:
        return json.loads(response)

def show_list(commands, raw_text=False):
    responses = []
    for command in commands:
        responses.append(show(command))

    return responses
