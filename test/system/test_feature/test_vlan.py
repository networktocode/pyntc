import sys
import os
import unittest

from pyntc.data_model.schemas import validate
from pyntc.errors import CommandError
from pyntc.features.vlans.base_vlans import VlanNotInRangeError

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from base_device_test import BaseDeviceTest

class TestVlan(BaseDeviceTest):

    def test_get_list(self):
        vlans = self.device.feature('vlans')
        vlan_list = vlans.get_list()
        validate(vlan_list, 'vlan_list')

    def test_get(self):
        vlans = self.device.feature('vlans')
        vlan = vlans.get('1')
        validate(vlan, 'vlan')

    def test_get_bad(self):
        vlans = self.device.feature('vlans')
        with self.assertRaises(VlanNotInRangeError):
            vlans.get('5000')

    def test_config(self):
        vlans = self.device.feature('vlans')
        vlans.config('10')

        vlan_list = vlans.get_list()
        self.assertIn('10', vlan_list)

    def test_config_bad(self):
        vlans = self.device.feature('vlans')
        with self.assertRaises(VlanNotInRangeError):
            vlans.config('5000')

    def test_config_with_name(self):
        vlans = self.device.feature('vlans')
        vlans.config('10', name='my_vlan')

        vlan_list = vlans.get_list()
        self.assertIn('10', vlan_list)

        the_vlan = vlans.get('10')
        self.assertEqual(the_vlan.get('name'), 'my_vlan')

    def test_get_all(self):
        vlans = self.device.feature('vlans')
        vlan_detail_list = vlans.get_all()

        validate(vlan_detail_list, 'vlan_detail_list')

    def test_set_name(self):
        vlans = self.device.feature('vlans')
        vlan_name = 'my_vlan_23'
        vlans.set_name('23', vlan_name)

        vlan_23 = vlans.get('23')
        self.assertEqual(vlan_23.get('name'), vlan_name)

    def test_remove(self):
        vlans = self.device.feature('vlans')
        vlans.config('10')

        vlan_list = vlans.get_list()
        self.assertIn('10', vlan_list)

        vlans.remove('10')
        vlan_list = vlans.get_list()
        self.assertNotIn('10', vlan_list)


def suite(conn_name):
    tests = ['test_get_list', 'test_get',
             'test_get_bad', 'test_config',
             'test_config_bad', 'test_config_with_name',
             'test_get_all', 'test_set_name',
             'test_remove']
    conn_list = [conn_name] * len(tests)
    return unittest.TestSuite(map(TestVlan, tests, conn_list))
