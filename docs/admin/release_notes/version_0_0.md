# v0.0 Release Notes

## [0.0.13]
### Added
- AIREOSDevice methods for disabling and enabling WLANs by ID (`disable_wlans`, `enable_wlans`)
- AIREOSDevice properties for getting disabled and enabled WLAN IDs (`disabled_wlans`, `enabled_wlans`)
- AIREOSDevice property for getting all WLANs (`wlans`)
### Changed
- AIREOSDevice `install_os` method now supports disabling and enabling WLANs before and after install respectively.

## [0.0.12]
### Added
- AIREOSDevice methods for pre-downloading images to Access Points (``transfer_image_to_ap``)
### Changed
- EOSDevice ``file_copy`` now uses Netmiko instead of custom code
- Code format was updated with new `black` release

##  [0.0.11]
### Added
- AIREOSDevice property, ``peer_redundancy_state`` for standby device status

### Changed
- AIREOSDevice ``os_install`` method verifies standby device is in same state as before install

## [0.0.10]
### Added
- Cisco WLC/AireOS Driver
- [Poetry](https://python-poetry.org/)
- `boot_options` property
### Changed
- Super calls migrated to Python 3 syntax
- Moved templates package inside of utils package
- Moved converters package inside of utils package
- Moved constants to modules that used them instead of having separate modules
### Deprecated
- The `get_boot_options` method; replaced by `boot_options` property
### Removed
- Support for Python 2
- `strip_unicode` function since support is not for Python 3
### Fixed
- All Unittests
- IOS `enable` method failure condition when disabled
### Security


## [0.0.9] - 2017-11-28
### Added
- Method to fully install an OS on a device.
- Support for dynamically determining a devices default file system to be used by methods that deal with file management.
- Several validations that ensure methods that perform actions on a device properly accomplished what they set out to do.
- Several Exception classes to report when methods do not accomplish what they attempted to do.
- Internal methods to "reconnect" to devices after a reboot; accepts a timeout to gauge if device takes longer than expected to boot up.
- Internal method to validate that the device has booted the specified image.
- Linting with Black
- Official versioning in __init__
### Changed
- Defaulting methods that manage files to default to using the devices default file system, while also allowing users to specfiy the file system.
- ASADevice to inherit from BaseDevice instead of IOSDevice.
- Changed TextFSM parsing to open files using a context manager.
### Fixed
- Issues with determining the boot variables for certain IOS versions and models.
- Issue where IOS devices only supported booting files in "flash:" file system.
- Issue with facts data not getting updated when calling the refresh_facts method.
