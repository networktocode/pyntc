# v3.0 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Pyntc now requires the `PYNTC_LOG_FILE` environment variable to output logging to a file. The new default behavior is to only log to stderr.

<!-- towncrier release notes start -->
## [v3.0.2 (2026-05-28)](https://github.com/networktocode/pyntc/releases/tag/v3.0.2)

### Added

- [#395](https://github.com/networktocode/pyntc/issues/395) - Added an ``install_mode`` property to ``BaseDevice`` (abstract) and ``IOSDevice``; the IOS implementation returns ``True`` when the device boots from ``packages.conf``.

### Deprecated

- [#395](https://github.com/networktocode/pyntc/issues/395) - Deprecated the ``install_mode`` argument to ``IOSDevice.install_os``; install mode is now derived from the device's ``boot_options`` via the new ``install_mode`` property and will be removed in a future release.

### Fixed

- [#394](https://github.com/networktocode/pyntc/issues/394) - Fixed Junos reboots not being detected when waiting for the device to reload.
- [#394](https://github.com/networktocode/pyntc/issues/394) - Increased the default Junos reboot wait timeout from 1 hour to 2 hours.

## [v3.0.1 (2026-05-26)](https://github.com/networktocode/pyntc/releases/tag/v3.0.1)

### Added

- [#387](https://github.com/networktocode/pyntc/issues/387) - Added an `NXOSDevice.show_netmiko` method and deprecated the existing `NXOSDevice.show` method that uses pynxos. Developers should transition to the `show_netmiko` method to prepare for the eventual removal of pynxos.

### Changed

- [#387](https://github.com/networktocode/pyntc/issues/387) - Changed the following NXOSDevice methods/properties to use Netmiko instead of pynxos: `_image_booted`, `_wait_for_device_reboot`, `uptime`, `hostname`, `os_version`, `_get_file_system`, `_get_free_space`, `remote_file_copy`, `redundancy_state`, `reboot`, `set_boot_options`, and `startup_config`.

### Fixed

- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed a bug in nxos where nx-api commands were mixed with ssh commands.
- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed a bug in nxos `_build_url_copy_command_simple` returning the wrong type of data.
- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed a bug in nxos failing to answer a prompt when using remote_file_copy.
- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed NXOSDevice.os_version to use netmiko SSH instead of NX-API.
- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed NXOSDevice.get_remote_checksum to use the correct `show file` command form and parse the digest out of the device output.
- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed NXOSDevice.save to use netmiko SSH instead of NX-API.
- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed NXOSDevice.show to use netmiko SSH instead of NX-API. Structured (non-`raw_text`) results are now TextFSM-parsed lists of dicts.
- [#387](https://github.com/networktocode/pyntc/issues/387) - Fixed NXOSDevice._wait_for_device_reboot to drop the pre-reboot SSH session and reconnect each poll so it reliably detects when the device comes back from a reload.

## [v3.0.0 (2026-05-06)](https://github.com/networktocode/pyntc/releases/tag/v3.0.0)

### Breaking Changes

- [#383](https://github.com/networktocode/pyntc/issues/383) - The pyntc rotating file handler is now opt-in via the `PYNTC_LOG_FILE` environment variable. When unset, no log file is created. When set, its value is used as the log file path, and the handler is registered only once per logger to avoid duplicate entries on repeated `get_log` calls.
