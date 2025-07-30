# v0.17 Release Notes

## [0.17.0]
### Added
- ASADevice supports connecting to HA Peer
- ASADevice `connected_interface`, `ip_address`, `ipv4_addresses`, `ipv6_addresses`, `ip_protocol`, `peer_device`, `peer_ip_address`, `peer_ipv4_addresses`, `peer_ipv6_addresses`, properties
- ASADevice `enable_scp`, `reboot_standby` methods
- IOSDevice now supports setting `fast_cli` on Netmiko driver
### Changed
- All Drivers `reboot` no longer accepts `confirm` argument
- AIREOSDevice ``transfer_image_to_ap`` attempts to check that install image matches expected value multiple times.
- ASADevice `file_copy` now supports transferring files to active and standby devices
- EOSDevice `config` method accepts a list of commands
- EOSDevice `show` method accepts a list of commands
- JUNOSDevice `config` method accepts a list of commands
- JUNOSDevice `show` method accepts a list of commands
### Fixed
- Account for additional output for verify if OS Image is booted
- Handle Upgrades by disabling `fast_cli` during reboot process