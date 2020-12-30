# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/)


## [Unreleased]
### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [0.16.0]
### Added
- ASADevice `is_active`, `peer_redundancy_state`, `redundancy_mode`, `redundancy_state` methods
### Changed
- AIREOSDevice `convert_filename_to_version` function now supports IRCM images

## [0.15.0]
### Added
- IOSDevice `os_install` method added support for using install mode
### Changed
- AIREOSDevice `config` method accepts a list of commands
- AIREOSDevice `config` method supports sending kwargs to netmiko
- AIREOSDevice `show` method accepts a list of commands
- AIREOSDevice `show` method supports sending kwargs to netmiko
- AIREOSDevice `file_copy` increased delay_factor default to 10
- IOSDevice `config` method accepts a list of commands
- IOSDevice `config` method supports sending kwargs to netmiko
- All devices `facts` property contents were converted to individual properties
### Deprecated
- AIREOSDevice `show_list` and `config_list` methods
- IOSDevice `config_list` method
- All Platforms `facts` property
- CommandListError class will migrate to just use CommandError
### Fixed
- IOSDevice `file_copy` method now reconnectes to device after transfer is complete to avoid sending commands across a closed SSH channel
- IOSDevice `peer_redundancy_state`, `redundancy_mode`, and `redundancy_state` all strip left spaces for regex match.

## [0.14.0]
### Added
- AIREOSDevice `show` method now supports sending any additional args that Netmiko supports using kwargs.
- AIREOSDevice `is_active` method was added to check if device is the active device.
- EOSDevice now supports specifying the connection port.
- IOSDevice `show` method now supports sending any additional args that Netmiko supports using kwargs.
- IOSDevice `is_active` method was added to check if device is currently the active in a HA setup.
- IOSDevice `redundancy_mode`, `redundancy_state`, and `peer_redundancy_properties` are now available.
### Changed
- AIREOSDevice sending commands with expected prompt is now done via Netmiko's `send_command` method.
- AIREOSDevice now waits for peer to form after upgrade before failing due to peer redundancy issues.
- AIREOSDevice `file_copy` method offers more granular failures to help identify where failures happen.
- AIREOSDevice `peer_redundancy_state` method now returns None if the unit does not support redundancy.
- AIREOSDevice `redundancy_state` method now returns a string of the state or None if it is not supported.
- AIREOSDevice `is_active` method should be used for functionality previously supported by `redundancy_state`.
- AIREOSDevice `open` method now allows the default behavior of checking that device is active to be turned off using `confirm_active` arg.
- AIREOSDevice `show` method no longer supports passing `expect` arg, as that is implied by passing `expect_string`.
- ASADevice sending commands with expected prompt is now done via Netmiko's `send_command` method.
- ASADevice `show` method no longer supports passing `expect` arg, as that is implied by passing `expect_string`.
- IOSDevice fetching the default file system now tries 5 times before raising an exception.
- IOSDevice sending commands with expected prompt is now done via Netmiko's `send_command` method.
- IOSDevice waiting for device to reboot now waits until "show version" command is successful (delayed startup).
- IOSDevice `file_copy` method will attempt md5 validation if copy completes even though network device closes the socket.
- IOSDevice `open` method now defaults to checking that device is active; use the `confirm_active` arg to change this.
- IOSDevice `show` method no longer supports passing `expect` arg, as that is implied by passing `expect_string`.

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
