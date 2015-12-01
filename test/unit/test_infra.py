import unittest

from ntc_lib import get_device
from ntc_lib.errors import UnsupportedDeviceError

vendor_list = ['nxos', 'eos']

BAD_VENDOR = '238nzsvkn3981'

class TestInfra(unittest.TestCase):

    def test_device_creation(self):
        for vendor in vendor_list:
            device = get_device(vendor)
            self.assertIsNot(device, None)

    def test_unsupported_device(self):
        with self.assertRaises(UnsupportedDeviceError):
            get_device(BAD_VENDOR)

