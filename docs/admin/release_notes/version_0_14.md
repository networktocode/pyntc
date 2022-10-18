# v0.14 Release Notes

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