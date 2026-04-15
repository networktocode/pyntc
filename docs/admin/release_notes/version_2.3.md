
# v2.3 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added the ability to for remote file copy on Cisco NXOS, Cisco ASA, and Arista EOS operating systems.

## [v2.3.0 (2026-04-14)](https://github.com/networktocode/pyntc/releases/tag/v2.3.0)

### Added

- [#365](https://github.com/networktocode/pyntc/issues/365) - Added the remote file copy feature to Arista EOS devices.
- [#365](https://github.com/networktocode/pyntc/issues/365) - Added unittests for remote file copy on Arista EOS devices.
- [#366](https://github.com/networktocode/pyntc/issues/366) - Added ``remote_file_copy``, ``check_file_exists``, ``get_remote_checksum``, and ``verify_file`` support for ``ASADevice`` (FTP, TFTP, SCP, HTTP, HTTPS).
- [#367](https://github.com/networktocode/pyntc/issues/367) - Added remote file copy feature to Cisco NXOS devices.
- [#367](https://github.com/networktocode/pyntc/issues/367) - Added unittests for remote file copy for Cisco NXOS devices.

### Changed

- [#368](https://github.com/networktocode/pyntc/issues/368) - Improved EOS remote file copy to validate scheme and query strings before connecting, use `clean_url` to prevent credential leakage, and simplify credential routing.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Changed copy command builders to include the source file path in the URL and use `flash:` as the destination, matching EOS CLI conventions.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Fixed `_uptime_to_string` to use integer division, preventing `ValueError` on format specifiers.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Fixed `check_file_exists` and `get_remote_checksum` to open the SSH connection before use, preventing `AttributeError` when called standalone.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Fixed password-prompt handling in `remote_file_copy` to wait for the transfer to complete before proceeding to verification.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Simplified checksum parsing in `get_remote_checksum` to use string splitting instead of regex.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Changed `verify_file` to return early when file does not exist and use case-insensitive checksum comparison.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Removed `include_username` parameter from `remote_file_copy` in favor of automatic credential routing based on scheme and username presence.

### Removed

- [#364](https://github.com/networktocode/pyntc/issues/364) - Removed log.init from iosxewlc device.
- [#364](https://github.com/networktocode/pyntc/issues/364) - Removed warning filter for logging.

### Fixed

- [#366](https://github.com/networktocode/pyntc/issues/366) - Fixed ``ASADevice._get_file_system`` to use ``re.search`` instead of ``re.match`` so the filesystem label is correctly parsed regardless of leading whitespace in ``dir`` output.
- [#366](https://github.com/networktocode/pyntc/issues/366) - Fixed ``ASADevice._send_command`` to anchor the ``%`` error pattern to the start of a line (``^% ``) to prevent false-positive ``CommandError`` raises during file copy operations.
- [#366](https://github.com/networktocode/pyntc/issues/366) - Fixed ``ASADevice.active_redundancy_states`` to include ``"disabled"`` so standalone (non-failover) units are correctly treated as active.

### Housekeeping

- [#368](https://github.com/networktocode/pyntc/issues/368) - Converted EOS remote file copy tests from hypothesis/pytest standalone functions to unittest TestCase with `self.assertRaises` and `subTest` for consistency with the rest of the codebase.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Removed duplicate test class `TestRemoteFileCopyCommandExecution` and consolidated into `TestRemoteFileCopy`.
- [#368](https://github.com/networktocode/pyntc/issues/368) - Added integration tests for EOS device connectivity and remote file copy across FTP, TFTP, SCP, HTTP, HTTPS, and SFTP protocols.
