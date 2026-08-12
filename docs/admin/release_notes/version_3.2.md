# v3.2 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added support for ISSU and NSSU non-disruptive OS upgrades on Juniper devices, along with several fixes to Juniper `install_os` and `remote_file_copy` handling.
- Fixed Arista EOS reboot detection when waiting for a device to reload.

<!-- towncrier release notes start -->
## [v3.2.3a0 (2026-08-12)](https://github.com/networktocode/pyntc/releases/tag/velease-3.2.3a0)

### Added

- [#413](https://github.com/networktocode/pyntc/issues/413) - Added Juniper SRX Chassis Cluster upgrade support when ICU.
- [#418](https://github.com/networktocode/pyntc/issues/418) - Added the `arista_eos_ssh` device type, an SSH-only Arista EOS driver for environments where eAPI is not enabled; it exposes the same API as `arista_eos_eapi` and obtains structured data via the CLI's `| json` pipe.

### Housekeeping

- Work on trusted publisher for networktocode org.

## [v3.2.2 (2026-08-04)](https://github.com/networktocode/pyntc/releases/tag/v3.2.2)

### Fixed

- [#410](https://github.com/networktocode/pyntc/issues/410) - Fixed checksum verification timing out on large OS images — `get_remote_checksum` and `verify_file` now accept a `read_timeout` argument and its default was raised from 300s to 900s for IOS, ASA and IOS-XR devices.

## [v3.2.1 (2026-07-27)](https://github.com/networktocode/pyntc/releases/tag/v3.2.1)

### Fixed

- [#407](https://github.com/networktocode/pyntc/issues/407) - Fixed Arista EOS reboots not being detected when waiting for the device to reload.

## [v3.2.0 (2026-07-14)](https://github.com/networktocode/pyntc/releases/tag/v3.2.0)

### Added

- [#400](https://github.com/networktocode/pyntc/issues/400) - Added support for ISSU and NSSU non-disruptive OS upgrades on Juniper devices.
- [#400](https://github.com/networktocode/pyntc/issues/400) - Added a `snapshot` option to `JunosDevice.install_os` that takes a post-upgrade `request system snapshot slice alternate` and waits for completion; disabled by default because Junos does not require a snapshot to complete an upgrade.

### Fixed

- [#400](https://github.com/networktocode/pyntc/issues/400) - Fixed `JunosDevice._get_free_space` raising `FileSystemNotFoundError` on virtual-chassis, multi-RE, and cluster devices; the smallest member's free space is now returned.
- [#400](https://github.com/networktocode/pyntc/issues/400) - Fixed `JunosDevice.remote_file_copy` discarding the device's actual error message on a failed copy; the underlying error is now included in the raised `FileTransferError`.
- [#400](https://github.com/networktocode/pyntc/issues/400) - Fixed `JunosDevice.remote_file_copy` failing with "filesystem is full" on small-flash platforms (e.g., EX switches); remote images are now downloaded directly to the destination path instead of being staged in the user's home directory on `/var`.
- [#400](https://github.com/networktocode/pyntc/issues/400) - Fixed `JunosDevice` post-install version verification failing on platforms whose `show version` output has no "JUNOS Base OS Software Suite" line (e.g., EX switches on 15.1).
- [#400](https://github.com/networktocode/pyntc/issues/400) - Fixed `JunosDevice.install_os` issuing a disruptive full-chassis reboot after an NSSU/ISSU upgrade, which already reboots each member in service during the install.
