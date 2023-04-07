# v1.0 Release Notes

## [1.0.0] 04-2023

### Added

- [270](https://github.com/networktocode/pyntc/pull/270) Add additional properties to ASA and AIREOS.
- [271](https://github.com/networktocode/pyntc/pull/271) Add default logging for all devices and overall library.
- [280](https://github.com/networktocode/pyntc/pull/280) Add the `wait_for_reload` argument from `reboot` method throughout library. Defaults to False to keep current code backward compatible, If set to True the reboot method waits for the device to finish the reboot before returning.

### Changed
- [280](https://github.com/networktocode/pyntc/pull/280) Changed from relative imports to absolute imports.
- [282](https://github.com/networktocode/pyntc/pull/282) Update initial pass at pylint.

### Deprecated

- [269](https://github.com/networktocode/pyntc/pull/269) Remove `show_list` and `config_list` methods asa and ios. Add default functionality to `show` and `config` to handle str and list.
- [275](https://github.com/networktocode/pyntc/pull/275) Remove python ABC (abstract base classes) as they were not required.
- [275](https://github.com/networktocode/pyntc/pull/275) Remove `show_list` and `config_list` methods for the rest of device drivers. Add default functionality to `show` and `config` to handle str and list.
- [280](https://github.com/networktocode/pyntc/pull/280) Remove the use of `signal` modules within Cisco drivers. This will allow for reboots to be able to be handled within threads.
- [280](https://github.com/networktocode/pyntc/pull/280) Remove the `timer` argument from `reboot` method throughout library. Compatibility matrix on which versions, vendors support it became to much to maintain.
