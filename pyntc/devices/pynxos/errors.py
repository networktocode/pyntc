class NXOSError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return "%s: %s" % (self.__class__.__name__, self.message)

    __str__ = __repr__


class CLIError(NXOSError):
    def __init__(self, command, message):
        self.command = command
        self.message = message

    def __repr__(self):
        return 'The command "%s" gave the error "%s".' % (self.command, self.message)

    __str__ = __repr__
