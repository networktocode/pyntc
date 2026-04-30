
# v2.4 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Add ability to check for sufficient free space before copying files to devices, with support for EOS, IOS, ASA, and JunOS platforms.
- Added reboot flag to Device.install_os for supported platforms.

## [v2.4.0 (2026-04-29)](https://github.com/networktocode/pyntc/releases/tag/v2.4.0)

### Added

- [#370](https://github.com/networktocode/pyntc/issues/370) - Added a pre-transfer free-space check to EOS ``file_copy`` and ``remote_file_copy`` that raises ``NotEnoughFreeSpaceError`` when the target filesystem lacks room for the image.
- [#370](https://github.com/networktocode/pyntc/issues/370) - Added ``file_size_unit`` (``bytes``, ``megabytes``, or ``gigabytes``; default ``bytes``) and a computed ``file_size_bytes`` to ``FileCopyModel`` so ``remote_file_copy`` can verify free space against a caller-supplied size; when ``file_size`` is omitted the pre-transfer check is skipped.
- [#371](https://github.com/networktocode/pyntc/issues/371) - Added free space validation for file copy operations on IOS devices.
- [#372](https://github.com/networktocode/pyntc/issues/372) - Added a pre-transfer free-space check to Cisco ASA ``file_copy`` and ``remote_file_copy`` that raises ``NotEnoughFreeSpaceError`` when the target filesystem lacks room for the image.
- [#373](https://github.com/networktocode/pyntc/issues/373) - Added a pre-transfer free-space check to Juniper JunOS ``file_copy`` and ``remote_file_copy`` that raises ``NotEnoughFreeSpaceError`` when the target filesystem lacks room for the image.
- [#375](https://github.com/networktocode/pyntc/issues/375) - Added free space validation for file copy operations on NXOS devices.
- [#376](https://github.com/networktocode/pyntc/issues/376) - Added reboot flag to Device.install_os for supported platforms.
- [#376](https://github.com/networktocode/pyntc/issues/376) - Vendored pynxos library and added reboot flag to Device.set_boot_options.

### Changed

- [#356](https://github.com/networktocode/pyntc/issues/356) - Bump dependencies
