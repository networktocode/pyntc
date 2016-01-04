import unittest
from pyntc import ntc_device_by_name

class BaseDeviceTest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        try:
            self.conn_name = args[1]
        except IndexError:
            raise Exception('Connection name not given.')
        super(BaseDeviceTest, self).__init__(args[0], **kwargs)

    def setUp(self, device=None):
        self.device = ntc_device_by_name(self.conn_name)
        self.device.open()

    def tearDown(self):
        self.device.close()
