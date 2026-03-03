# v0.15 Release Notes

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