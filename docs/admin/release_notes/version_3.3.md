# v3.3 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release adds Juniper SRX Chassis Cluster upgrade support via ICU and introduces a new `arista_eos_ssh` device type, an SSH-only Arista EOS driver that mirrors the `arista_eos_eapi` API for environments without eAPI. It also fixes a security issue where source server passwords were logged during FTP/HTTP/HTTPS file copies to Cisco IOS devices.

<!-- towncrier release notes start -->
## [v3.3.0 (2026-10-01)](https://github.com/networktocode/pyntc/releases/tag/v3.3.0)

### Added

- [#413](https://github.com/networktocode/pyntc/issues/413) - Added Juniper SRX Chassis Cluster upgrade support when ICU.
- [#418](https://github.com/networktocode/pyntc/issues/418) - Added the `arista_eos_ssh` device type, an SSH-only Arista EOS driver for environments where eAPI is not enabled; it exposes the same API as `arista_eos_eapi` and obtains structured data via the CLI's `| json` pipe.

### Security

- [#429](https://github.com/networktocode/pyntc/issues/429) - Stopped the source server password appearing in the logs during an FTP, HTTP or HTTPS file copy to Cisco IOS devices.

### Changed

- [#426](https://github.com/networktocode/pyntc/issues/426) - Kept the byte counts on `NotEnoughFreeSpaceError` as attributes (`required`, `available`, `file_system`, `shortfall`) so callers no longer have to parse the message, and its message now reports those counts with thousands separators along with the remaining shortfall.
- [#429](https://github.com/networktocode/pyntc/issues/429) - Raised the minimum supported netmiko version to 4.4.

### Fixed

- [#429](https://github.com/networktocode/pyntc/issues/429) - Fixed remote file copy failures on Cisco IOS, NX-OS, ASA and IOS-XR reporting a generic message instead of the error the device returned.
- [#429](https://github.com/networktocode/pyntc/issues/429) - Fixed FTP, HTTP and HTTPS file transfers to Cisco IOS devices failing to authenticate.
- [#429](https://github.com/networktocode/pyntc/issues/429) - Fixed remote file copy hanging on Cisco IOS and NX-OS when a device returned output the driver did not recognize.
