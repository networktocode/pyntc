import signal

from .base_device import BaseDevice
from pyntc.errors import CommandError, NTCError

from netmiko import ConnectHandler
from netmiko import FileTransfer

class FileTransferError(NTCError):
    pass

class RebootSignal(NTCError):
    pass

class IOSDevice(BaseDevice):
    def __init__(self, host, username, password, port=22, **kwargs):
        super(IOSDevice, self).__init__(host, username, password, vendor='Cisco', device_type='ios')

        self.native = None

        self.host = host
        self.username = username
        self.password = password
        self.port = int(port)
        self.open()

    def open(self):
        self.native = ConnectHandler(device_type='cisco_ios',
                                     ip=self.host,
                                     username=self.username,
                                     password=self.password,
                                     port=self.port,
                                     verbose=False)

    def close(self):
        self.native.disconnect()

    def _enter_config(self):
        if not self.native.check_config_mode():
            self.native.config_mode()

    def _enable(self):
        if self.native.check_config_mode():
            self.native.exit_config_mode()

        if not self.native.check_enable_mode():
            self.native.enable()

    def _send_command(self, command):
        response = self.native.send_command(command)
        if response[0] == '%':
            raise CommandError(response)

        return response

    def config(self, command):
        self._enter_config()
        self._send_command(command)
        self.native.exit_config_mode()

    def config_list(self, commands):
        self._enter_config()
        for command in commands:
            self._send_command(command)
        self.native.exit_config_mode()

    def show(self, command):
        self._enable()
        return self._send_command(command)

    def show_list(self, commands):
        self._enable()

        responses = []
        for command in commands:
            responses.append(self._send_command(command))

        return responses

    def save(self, filename='startup-config'):
        self.show_list(['copy running-config %s' % filename, '\n'])

    def file_copy(self, src, dest=None):
        if dest is None:
            dest = src
        fc = FileTransfer(self.native, src, dest)
        if not fc.verify_space_available():
            raise FileTransferError('Not enough space available.')
        if fc.check_file_exists() and fc.compare_md5():
            return

        fc.enable_scp()
        fc.establish_scp_conn()
        fc.transfer_file()
        fc.close_scp_chan()

    def reboot(self, timer=0, confirm=False):
        if confirm:
            def handler(signum, frame):
                raise RebootSignal('Interupting after reload')

            signal.signal(signal.SIGALRM, handler)
            signal.alarm(10)

            try:
                if timer > 0:
                    first_response = self.show('reload in %d' % timer)
                else:
                    first_response = self.show('reload')

                if 'System configuration' in first_response:
                    self.native.send_command('no')

                self.native.send_command('\n')
            except RebootSignal:
                signal.alarm(0)

            signal.alarm(0)
        else:
            print('Need to confirm reboot with confirm=True')

    def install_os(self, image_name, **vendor_specifics):
        self.config('boot system' % image_name)

    def backup_running_config(self, filename):
        with open(filename, 'w') as f:
            f.write(self.running_config)

    @property
    def facts(self):
        pass

    @property
    def running_config(self):
        return self.show('show running-config')

    @property
    def startup_config(self):
        return self.show('show startup-config')
