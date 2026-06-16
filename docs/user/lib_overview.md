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

!!! note "IOS-XR upgrades require a golden ISO"
    The `cisco_iosxr_ssh` driver (`IOSXRDevice`) performs eXR OS upgrades using the
    asynchronous native install workflow (`install add` → poll → `install activate` →
    poll → reload → `install commit` → verify).

    The driver upgrades from a single **golden ISO**. On eXR a bare base ISO
    **cannot be activated on its own** when optional feature packages (IS-IS, OSPF,
    MPLS, multicast, etc.) are active: `install activate` aborts demanding the
    matching-version RPMs be activated in the same operation. A golden ISO solves
    this by bundling the base XR image and the matching feature RPMs into one file,
    so it activates cleanly without supplying separate packages:

    ```python
    device.install_os("ncs5k-golden-x-7.11.2-NTC7112.iso")
    ```

    The golden ISO must already be staged on `harddisk:` (use `remote_file_copy`).
    Installing a base ISO plus separate feature RPMs is **not** supported by this
    driver.

!!! tip "Building a golden ISO with gisobuild"
    Build a golden ISO with Cisco's [gisobuild](https://github.com/ios-xr/gisobuild)
    tool. Provide the platform's base (`mini`) ISO, a repository of the matching
    feature RPMs you want bundled, a label (which becomes part of the resulting
    filename), and an output directory:

    ```bash
    ntc@linux-server:~/xr/gisobuild$ mkdir -p /home/ntc/xr/7.11.1/giso_out

    ./src/gisobuild.py \
      --iso /home/ntc/xr/7.11.1/ncs5k-mini-x-7.11.1.iso \
      --repo /home/ntc/xr/7.11.1/ \
      --pkglist ncs5k-isis-1.0.0.0-r7111.x86_64.rpm \
                ncs5k-ospf-1.0.0.0-r7111.x86_64.rpm \
                ncs5k-mpls-1.0.0.0-r7111.x86_64.rpm \
                ncs5k-mpls-te-rsvp-1.0.0.0-r7111.x86_64.rpm \
                ncs5k-mcast-1.0.0.0-r7111.x86_64.rpm \
                ncs5k-mgbl-1.0.0.0-r7111.x86_64.rpm \
                ncs5k-m2m-1.0.0.0-r7111.x86_64.rpm \
      --label NTC711 \
      --out-directory /home/ntc/xr/7.11.1/giso_out \
      --create-checksum \
      --clean \
      --docker
    ```

    On success gisobuild writes the golden ISO (e.g.
    `ncs5k-golden-x-7.11.1-NTC711.iso`) into the output directory. Publish that file
    to the server `remote_file_copy` pulls from, then pass its filename to
    `install_os`.
