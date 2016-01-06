import unittest
import sys
import os

from pyntc import _get_config_from_file, LIB_PATH_ENV_VAR
from pyntc.devices import supported_devices, DEVICE_CLASS_KEY

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures')
CONF_FILE = os.path.join(FIXTURES_DIR, '.ntc.conf')
os.environ[LIB_PATH_ENV_VAR] = CONF_FILE


def write_err(string):
    sys.stderr.write(string)
    sys.stderr.write('\n')
    sys.stderr.flush()

import test_devices
sys.path.append(os.path.join(os.path.dirname(__file__), 'test_feature'))
import test_vlan

device_config = _get_config_from_file()[0]
config_sections = device_config.sections()
conn_names = list(x.split(':')[1] for x in config_sections)

test_runner = unittest.TextTestRunner(verbosity=2)

for conn_name in conn_names:
    write_err('Testing device \'%s\'' % conn_name)
    write_err('=' * 40)

    write_err('Testing Device Functions')
    test_runner.run(test_devices.suite(conn_name))

    write_err('Test Vlan Functions')
    test_runner.run(test_vlan.suite(conn_name))
