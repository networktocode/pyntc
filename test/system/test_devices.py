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

    def test_config(self):
        pass

    def test_config_list(self):
        pass

    def test_show(self):
        pass

    def test_show_list(self):
        pass

    def test_facts(self):
        for device in self.devices:
            facts = device.facts
            validate(facts, 'facts')






