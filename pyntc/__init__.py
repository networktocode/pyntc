"""Kickoff functions for getting instancs of device objects.
"""

import os
import warnings

from .devices import supported_devices
from .errors import UnsupportedDeviceError, DeviceNameNotFoundError, ConfFileNotFoundError

try:
    from configparser import ConfigParser as SafeConfigParser
except ImportError:
    from ConfigParser import SafeConfigParser

__version__ = "0.17.0"

LIB_PATH_ENV_VAR = "PYNTC_CONF"
LIB_PATH_DEFAULT = "~/.ntc.conf"


warnings.simplefilter("default")


def ntc_device(device_type, *args, **kwargs):
    """Instantiate and return an instance of a device subclassed
    from ``pyntc.devices.BaseDevice``. ``*args`` and ``*kwargs`` are passed
    directly to the device initializer.

    Arguments:
        device_type (string): A valid device_type
            listed in ``pyntc.devices.supported_devices``

    Returns:
        An instance of a subclass of ``pyntc.devices.BaseDevice``.

    Raises:
        UnsupportedDeviceError: if the device_type is unsupported.
    """

    try:
        device_class = supported_devices[device_type]
        return device_class(*args, **kwargs)
    except KeyError:
        raise UnsupportedDeviceError(device_type)


def ntc_device_by_name(name, filename=None):
    """Instantiate and return an instance of a device subclassed
    from ``pyntc.devices.BaseDevice`` based on its name in an
    NTC configuration file.

    If no filename is given the environment variable PYNTC_CONF is checked
    for a path, and then ~/.ntc.conf.

    Arguments:
        name (string): Name of the device as listed in teh NTC configuration file.
        filename (string): (Optional) Path to NTC configuration file that includes
            the ``name`` argument as section header.

    Raises:
        DeviceNameNotFoundError: if the name is not found in the
            NTC configuration file.
        ConfFileNotFoundError: if no NTC configuration can be found.
    """
    config, filename = _get_config_from_file(filename=filename)
    sections = config.sections()

    if not sections:
        raise ConfFileNotFoundError(filename)

    for section in sections:
        if ":" in section:
            device_type_and_conn_name = section.split(":")
            device_type = device_type_and_conn_name[0]
            conn_name = device_type_and_conn_name[1]

            if name == conn_name:
                device_kwargs = dict(config.items(section))
                if "host" not in device_kwargs:
                    device_kwargs["host"] = name

                return ntc_device(device_type, **device_kwargs)

    raise DeviceNameNotFoundError(name, filename)


def _get_config_from_file(filename=None):
    if filename is None:
        if LIB_PATH_ENV_VAR in os.environ:
            filename = os.path.expanduser(os.environ[LIB_PATH_ENV_VAR])
        else:
            filename = os.path.expanduser(LIB_PATH_DEFAULT)

    config = SafeConfigParser()
    config.read(filename)

    return config, filename
