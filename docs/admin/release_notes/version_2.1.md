
# v2.1 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Adding the ability to perform file downloads in Cisco IOS. This enhances OS Upgrades and file operations greatly!

## [v2.1.0 (2026-03-03)](https://github.com/networktocode/pyntc/releases/tag/v2.1.0)

### Added

- [#345](https://github.com/networktocode/pyntc/issues/345) - Added the ability to download files from within a Cisco IOS device.

### Housekeeping

- [#335](https://github.com/networktocode/pyntc/issues/335) - Replaced black, bandit, flake8 and pydocstyle with ruff.
- [#335](https://github.com/networktocode/pyntc/issues/335) - Updated tasks.py with newest task list.
- [#335](https://github.com/networktocode/pyntc/issues/335) - Updated to using pyinvoke for development environment definition.
- Fixed docs build and code-reference issues.
- Rebaked from the cookie `main`.
