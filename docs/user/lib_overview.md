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
- Cisco NX-OS - uses pynxos (NX-API)
- Arista EOS - uses pyeapi (eAPI)
- Juniper Junos - uses PyEz (NETCONF)
- F5 Networks - uses f5-sdk (ReST)
