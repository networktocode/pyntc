import unittest
import os

from pyntc import ntc_device, ntc_device_by_name, get_config_from_file
from pyntc.errors import UnsupportedDeviceError
from pyntc.devices import supported_devices, DEVICE_CLASS_KEY
from pyntc.devices import BaseDevice, EOSDevice, NXOSDevice


BAD_DEVICE_TYPE = '238nzsvkn3981'
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures')

class TestInfra(unittest.TestCase):

    def test_device_creation(self):
        for device_type in supported_devices:
            device = ntc_device(device_type, 'host', 'user', 'pass')
            self.assertIsInstance(device, supported_devices[device_type][DEVICE_CLASS_KEY])

    def test_unsupported_device(self):
        with self.assertRaises(UnsupportedDeviceError):
            ntc_device(BAD_DEVICE_TYPE)

    def test_device_by_name(self):
        config_filepath = os.path.join(FIXTURES_DIR, '.ntc.conf.sample')

        nxos_device = ntc_device_by_name('test_nxos', filename=config_filepath)
        self.assertIsInstance(nxos_device, NXOSDevice)

        eos_device = ntc_device_by_name('test_eos', filename=config_filepath)
        self.assertIsInstance(eos_device, EOSDevice)
