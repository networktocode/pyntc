import unittest
import os

from pyntc import get_config_from_file, get_device_by_name
from pyntc.devices import supported_devices, DEVICE_CLASS_KEY, VENDOR_KEY
from pyntc.data_model.schemas import validate

class TestDevices(unittest.TestCase):
    def setUp(self):
        device_config = get_config_from_file()
        config_sections = device_config.sections()

        device_names = list(x.split(':')[1] for x in config_sections)
        self.devices = list(get_device_by_name(x) for x in device_names)

        for device in self.devices:
            device.open()

    def tearDown(self):
        for device in self.devices:
            device.close()

    def test_facts(self):
        for device in self.devices:
            validate(device.facts, 'facts')

    def test_running_config(self):
        for device in self.devices:
            running_config = device.running_config
            self.assertGreater(len(running_config) > 0)
