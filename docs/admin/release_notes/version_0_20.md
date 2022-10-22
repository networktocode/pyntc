# v0.20 Release Notes

## [0.20.3] 10-21-2022

### Changed

- [250](https://github.com/networktocode/pyntc/pull/250) update full project to new dev standards.

### Deprecated
- [250](https://github.com/networktocode/pyntc/pull/250) remove support for py36.


## [0.20.2]

### Fixed

- Fixed ios device install mode run command.

## [0.20.1]

### Fixed

- Tox pipeline black linting issue.

## [0.20.0]

### Fixed

- Add a higher timeout to install os for nexus to cope with N5Ks slow response time.

### Added

- kwargs to pynxos native init to allow for additional arguments, such as `verify=False` for nxos.