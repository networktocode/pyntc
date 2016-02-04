import os
import json
from pyeapi.eapilib import CommandError as EOSCommandError

CURRNENT_DIR = os.path.dirname(os.path.realpath(__file__))


def enable(commands, encoding='json'):
    responses = []
    executed_commands = []
    for command in commands:
        command = command.replace(' ', '_')
        path = os.path.join(CURRNENT_DIR, 'enable' + '_' + encoding, command)

        executed_commands.append(command)
        if not os.path.isfile(path):
            raise EOSCommandError(1002, '%s failed' % command, commands=executed_commands)

        with open(path, 'r') as f:
            response = f.read()

        responses.append(response)

    response_string = ','.join(responses)
    response_string = '[' + response_string + ']'

    return json.loads(response_string)


def config(commands):
    responses = []
    executed_commands = []
    for command in commands:
        command = command.replace(' ', '_')
        path = os.path.join(CURRNENT_DIR, 'config', command)

        executed_commands.append(command)
        if not os.path.isfile(path):
            raise EOSCommandError(1002, '%s failed' % command, commands=executed_commands)


        responses.append({})

    return responses
