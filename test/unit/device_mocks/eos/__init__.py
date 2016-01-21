import os
from pyeapi.eapilib import CommandError as EOSCommandError

CURRNENT_DIR = os.path.realpath(__file__)


def enable(command, encoding='json'):
    command = command.replace(' ', '_')
    path = os.path.join(CURRNENT_DIR, 'enable' + '_' + encoding, command)

    with open(path, 'r') as f:
        response = f.read()

    return response


def config(commands):
    responses = []
    for command in commands:
        command = command.replace(' ', '_')
        path = os.path.join(CURRNENT_DIR, 'config', command)

        if not os.path.isfile(path):
            raise EOSCommandError

        responses.append({})

    return responses