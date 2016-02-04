import os

CURRNENT_DIR = os.path.dirname(os.path.realpath(__file__))


def send_command(command):
    command = command.replace(' ', '_')
    command = command.replace('/', '_')

    if command == '\n':
        command = 'return'

    path = os.path.join(CURRNENT_DIR, 'send_command', command)

    if not os.path.isfile(path):
        return '% Error: mock error'

    with open(path, 'r') as f:
        response = f.read()

    return response


