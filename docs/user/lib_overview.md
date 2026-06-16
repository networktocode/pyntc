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
- Cisco IOS-XR (eXR / 64-bit) - uses netmiko (SSH)
- Cisco NX-OS - uses pynxos (NX-API)
- Arista EOS - uses pyeapi (eAPI)
- Juniper Junos - uses PyEz (NETCONF)
- F5 Networks - uses f5-sdk (ReST)

!!! note "IOS-XR upgrades: install the base ISO plus matching feature RPMs"
    The `cisco_iosxr_ssh` driver (`IOSXRDevice`) performs eXR OS upgrades using the
    asynchronous native install workflow (`install add` → poll → `install activate` →
    poll → reload → `install commit` → verify).

    On eXR the base ISO **cannot be activated on its own** when optional feature
    packages (IS-IS, OSPF, MPLS, multicast, etc.) are active: `install activate`
    aborts demanding the matching-version RPMs be activated in the same operation.
    Pass those RPMs via the `additional_files` argument to `install_os` so the base
    ISO and the RPMs are added and activated together:

    ```python
    device.install_os(
        "ncs5k-mini-x-7.11.2.iso",
        additional_files=[
            "ncs5k-isis-2.1.0.0-r7112.x86_64.rpm",
            "ncs5k-ospf-2.1.0.0-r7112.x86_64.rpm",
            # ... the remaining matching-version feature RPMs
        ],
    )
    ```

    All files (ISO + RPMs) must already be staged on `harddisk:` (use
    `remote_file_copy` for each). Omitting the RPMs on a device that runs feature
    packages will cause `install activate` to abort.

!!! warning "Nautobot OS Upgrades passes a single image today"
    The Nautobot OS Upgrades `InstallOsJob` currently passes a single image to
    `install_os` and does not yet supply `additional_files`. Driving an eXR upgrade
    through that app will therefore attempt an ISO-only activation and abort on any
    device with feature packages. Multi-file support in OS Upgrades is tracked as
    separate follow-up work.
