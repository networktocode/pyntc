import unittest
import os

from pyntc import get_device, get_device_by_name
from pyntc.devices import NXOSDevice, EOSDevice
from pyntc.errors import UnsupportedDeviceError

vendor_list = ['nxos', 'eos']

BAD_VENDOR = '238nzsvkn3981'
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures')

class TestInfra(unittest.TestCase):

    def test_device_creation(self):
        for vendor in vendor_list:
            device = get_device(vendor, 'host', 'user', 'pass')
            self.assertIsNot(device, None)

    def test_unsupported_device(self):
        with self.assertRaises(UnsupportedDeviceError):
            get_device(BAD_VENDOR)

    def test_device_by_name(self):
        config_filepath = os.path.join(FIXTURES_DIR, '.ntclib.conf')

        nxos_device = get_device_by_name('n9k1', config_filepath)
        self.assertIsInstance(nxos_device, NXOSDevice)

        eos_device = get_device_by_name('spine1', config_filepath)
        self.assertIsInstance(eos_device, EOSDevice)

