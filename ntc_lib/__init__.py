import os

from .devices.eos_device import EOSDevice
from .devices.nxos_device import NXOSDevice
from .errors import UnsupportedDeviceError

try:
    from configparser import ConfigParser as SafeConfigParser
except ImportError:
    from ConfigParser import SafeConfigParser

LIB_PATH_ENV_VAR = 'NTC_LIB_CONF'

def get_device(vendor, *args, **kwargs):
    device_map = {
        'nxos': NXOSDevice,
        'eos': EOSDevice,
    }
    try:
        device_class = device_map[vendor.lower()]
        return device_class(*args, **kwargs)
    except KeyError:
        raise UnsupportedDeviceError(vendor)


def get_device_by_name(name, filename=None):
    if filename is None:
        if LIB_PATH_ENV_VAR in os.environ:
            filename = os.path.expanduser(os.environ[LIB_PATH_ENV_VAR])
        else:
            filename = os.path.expanduser('~/.ntclib.conf')

    config = SafeConfigParser()
    config.read(filename)
    sections = config.sections()

    if not sections:
        return None

    for section in sections:
        if ':' in section:
            vendor_and_conn_name = section.split(':')
            vendor = vendor_and_conn_name[0]
            conn_name = vendor_and_conn_name[1]

            if name == conn_name:
                device_kwargs = dict(config.items(section))
                if 'host' not in device_kwargs:
                    device_kwargs['host'] = name

                return get_device(vendor, **device_kwargs)
