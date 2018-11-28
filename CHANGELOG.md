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
