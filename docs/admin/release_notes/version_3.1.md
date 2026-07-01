# v3.1 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added support for Cisco IOS-XR.

<!-- towncrier release notes start -->
## [v3.1.0 (2026-07-02)](https://github.com/networktocode/pyntc/releases/tag/v3.1.0)

### Added

- [#398](https://github.com/networktocode/pyntc/issues/398) - Added native Cisco IOS-XR (eXR / 64-bit) support via the `cisco_iosxr_ssh` driver (`IOSXRDevice`), including `remote_file_copy` (FTP/TFTP/SCP/HTTP/HTTPS) and OS upgrades from a single golden ISO (built with Cisco's gisobuild tool) through the asynchronous `install add` / `install activate` / `install commit` workflow.
