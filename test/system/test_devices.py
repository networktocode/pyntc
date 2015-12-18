import unittest
from pyntc.data_model.schemas import validate
from base_device_test import BaseDeviceTest

class TestDevices(BaseDeviceTest):

    def test_facts(self):
        validate(self.device.facts, 'facts')

    def test_running_config(self):
        running_config = self.device.running_config
        self.assertGreater(len(running_config), 0)


def suite(conn_name):
    tests = ['test_facts', 'test_running_config']
    conn_list = [conn_name] * len(tests)
    return unittest.TestSuite(map(TestDevices, tests, conn_list))
