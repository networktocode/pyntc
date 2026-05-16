# Library Overview

pyntc is an open source multi-vendor Python library that establishes a common framework for working with different network APIs & device types (including IOS devices)

It's main purpose is to simplify the execution of common tasks including:

- Executing commands
- Copying files
- Upgrading devices
- Rebooting devices
- Saving / Backing Up Configs

## Supported Platforms

- Cisco AireOS - uses netmiko (SSH)
- Cisco ASA - uses netmiko (SSH)
- Cisco IOS platforms - uses netmiko (SSH)
- Cisco NX-OS - migrating from pynxos (NX-API) to netmiko (SSH); see [NXOS transport change](#nxos-transport-change) below
- Arista EOS - uses pyeapi (eAPI)
- Juniper Junos - uses PyEz (NETCONF)
- F5 Networks - uses f5-sdk (ReST)

## NXOS transport change

`NXOSDevice` is migrating from the pynxos (NX-API) transport to Netmiko SSH. The migration is being delivered in phases:

- The `save()` method has been reimplemented on Netmiko SSH.
- The constructor still accepts the `transport`, `verify`, and `port` kwargs for backwards compatibility, but supplying any of them now emits a `DeprecationWarning`. These kwargs will be removed in a future release and will be ignored once the migration completes.
- The remaining NX-API call sites (`show`, `config`, `facts`-derived properties, `boot_options`, `reboot`, etc.) are still wired through pynxos and will be migrated in follow-up releases.

### Behavioral differences to expect once migration completes

- `show(..., raw_text=False)` will return TextFSM-parsed structures (via `ntc-templates`) rather than NX-API JSON. The result shape may differ for some commands; verify against `ntc-templates` output for the relevant `show` command.
- Properties derived from facts (`uptime`, `hostname`, `model`, `os_version`, etc.) will issue an SSH round trip on first access rather than reading from an NX-API JSON payload, and may not be populated until called.
- Niche `show` commands without an `ntc-templates` parser will return raw text; callers that relied on NX-API structured output may need to switch to `raw_text=True` and parse themselves.

See the corresponding entry in the release notes for the change-tracking fragment.
