# v3.0 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Pyntc now requires the `PYNTC_LOG_FILE` environment variable to output logging to a file. The new default behavior is to only log to stderr.

<!-- towncrier release notes start -->
## [v3.0.0 (2026-05-06)](https://github.com/networktocode/pyntc/releases/tag/v3.0.0)

### Breaking Changes

- [#383](https://github.com/networktocode/pyntc/issues/383) - The pyntc rotating file handler is now opt-in via the `PYNTC_LOG_FILE` environment variable. When unset, no log file is created. When set, its value is used as the log file path, and the handler is registered only once per logger to avoid duplicate entries on repeated `get_log` calls.
