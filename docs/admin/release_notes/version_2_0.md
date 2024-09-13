# v2.0 Release Notes

## [2.0.0] 12-2023
### Added
- [308](https://github.com/networktocode/pyntc/pull/308) nxos `refresh()` method to refresh device facts.
- [289](https://github.com/networktocode/pyntc/pull/289) additional cisco_ios boot options search.

### Changed
- [308](https://github.com/networktocode/pyntc/pull/308) Updated nxos install_os and logic when waiting for device reload and improved log messages.

### Deprecated
- [308](https://github.com/networktocode/pyntc/pull/308) Deprecated netmiko argument `delay_factor` in favor of `read_timeout` as per changes in Netmiko 4.0.

  Refer to this blog post for more info about changes in netmiko 4.0: https://pynet.twb-tech.com/blog/netmiko-read-timeout.html


## [2.0.1] 09-2024
### Added
- [311](https://github.com/networktocode/pyntc/pull/311) Extend cisco_ios set_boot_options method.

### Fixed
- [312](https://github.com/networktocode/pyntc/pull/312) Fix Arista EOS file copy issues.
