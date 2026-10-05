# v3.4 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added install_os method override for the SSH Arista driver.
- Add a method to check for Arista maintenance_mode.

<!-- towncrier release notes start -->
## [v3.4.0 (2026-10-05)](https://github.com/networktocode/pyntc/releases/tag/v3.4.0)

### Added

- Added install_os method for EOSSSHDevice class.
- Added maintenance_mode method for EOSSSHDevice class.

### Fixed

- [#423](https://github.com/networktocode/pyntc/issues/423) - Fixed `EOSDevice.close()` leaking the Netmiko SSH session opened by the file-transfer methods.

### Housekeeping

- Rebaked from the cookie `main`.
