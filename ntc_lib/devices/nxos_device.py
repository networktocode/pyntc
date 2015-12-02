from .base_device import BaseDevice

class NXOSDevice(BaseDevice):
    def __init__(self,
                 username='cisco',
                 password='cisco',
                 ip='192.168.200.50',
                 protocol='http',
                 timeout=30):

        if protocol not in ('http', 'https'):
            raise ValueError('protocol must be http or https')

        self.username = username
        self.password = password
        self.ip = ip
        self.protocol = protocol
        self.timeout = timeout
        self.sw1 = NXAPI()
        self.sw1.set_target_url('%s://%s/ins' % (self.protocol, self.ip))
        self.sw1.set_username(self.username)
        self.sw1.set_password(self.password)
        self.sw1.set_timeout(self.timeout)

    def open(self):
        pass

    def cli_error_check(self, data_dict):
        clierror = None
        msg = None

        error_check_list = data_dict['ins_api']['outputs']['output']
        try:
            for each in error_check_list:
                clierror = each.get('clierror', None)
                msg = each.get('msg', None)
        except AttributeError:
            clierror = error_check_list.get('clierror', None)
            msg = error_check_list.get('msg', None)

        if clierror:
            return CLIError(clierror, msg)

    def show(self, command, fmat='xml', text=False):
        if text is False:
            self.sw1.set_msg_type('cli_show')
        elif text:
            self.sw1.set_msg_type('cli_show_ascii')

        self.sw1.set_out_format(fmat)
        self.sw1.set_cmd(command)

        data = self.sw1.send_req()

        if fmat == 'xml':
            data_dict = xmltodict.parse(data[1])
        elif fmat == 'json':
            data_dict = json.loads(data[1])

        clierror = self.cli_error_check(data_dict)
        if clierror:
            raise clierror

        return data

    def config(self, command, fmat='xml'):
        self.sw1.set_msg_type('cli_conf')
        self.sw1.set_out_format(fmat)
        self.sw1.set_cmd(command)

        data = self.sw1.send_req()
        # return self.sw1.send_req
        if fmat == 'xml':
            data_dict = xmltodict.parse(data[1])
        elif fmat == 'json':
            data_dict = json.loads(data[1])

        clierror = self.cli_error_check(data_dict)
        if clierror:
            raise clierror

        return data
