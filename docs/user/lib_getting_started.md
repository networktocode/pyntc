# Getting Started with the Library

There are two ways to get started with pyntc.

The first way is to use the `ntc_device` object. Just pass in all required parameters to the object to initialize your device.  Here we are showing the import, but renaming the object to `NTC`.

```python
>>> from pyntc import ntc_device as NTC
>>>
```

Like many libraries, we need to pass in the host/IP and credentials.  Because this is a multi-vendor/API library, we also use the `device_type` parameter to identify which device we are building an instance of.

pyntc currently supports seven device types:

- cisco_aireos_ssh
- cisco_asa_ssh
- cisco_ios_ssh
- cisco_nxos_nxapi
- arista_eos_eapi
- juniper_junos_netconf
- f5_tmos_icontrol

The example below shows how to build a device object when working with a Cisco IOS router.

```python
>>> # CREATE DEVICE OBJECT FOR AN IOS DEVICE
>>>
>>> csr1 = NTC(host='csr1', username='ntc', password='ntc123', device_type='cisco_ios_ssh')
>>>
```

And here is an object for a Cisco Nexus device:

```python
>>> # CREATE DEVICE OBJECT FOR A NEXUS DEVICE
>>>
>>> nxs1 = NTC(host='nxos-spine1', username='ntc', password='ntc123', device_type='cisco_nxos_nxapi')
>>>
```

The second way to get started with pyntc is to use the pyntc configuration file.  This was modeled after Arista's `.eapi.conf` file.  Our file is called `.ntc.conf`

This simplifies creating device objects since you no longer need to specify credentials and other device specific parameters when you build the device object.  Instead, they are stored in the conf file.


# pyntc Configration File

- filename:  `.ntc.conf`
- Priority of locating the conf file:
    - `filename` param in `ntc_device_by_name`
    - Environment Variable aka `PYNTC_CONF`
    - Home directory `.ntc.conf`
- Specify device_type and a name
- host is not required if the name is the device's FQDN
- Four supported device types: `cisco_nxos_nxapi`, `cisco_ios_ssh`, `arista_eos_eapi`, and `juniper_junos_netconf`

Here is an example `.ntc.conf` file:

```ini
[cisco_nxos_nxapi:nxos-spine1]
host: 31.220.64.117
username: ntc
password: ntc123
transport: http

[cisco_ios_ssh:csr1]
host: 176.126.88.94
username: ntc
password: ntc123
port: 22

[juniper_junos_netconf:vmx1]
host: 176.126.88.99
username: ntc
password: ntc123

```

We can now build device objects just by referencing the name of the device from the conf file.

```python
>>> from pyntc import ntc_device_by_name as NTCNAME
>>>
>>> csr1 = NTCNAME('csr1')
>>>
>>> nxs1 = NTCNAME('nxos-spine1')
>>>
>>> vmx1 = NTCNAME('vmx1')
```

Once the device object is creating using either `ntc_device` or `ntc_device_by_name`, you can start using the built-in device methods in pyntc.

!!! info
    The only method and property not supported on all devices is `install_os`.  It is not supported on Juniper Junos devices.

### Gathering Facts

- Use `facts` device property

On a Nexus device:

```python
>>> nxs1 = NTCNAME('nxos-spine1')
>>>
>>> nxs1.facts
{'vendor': 'cisco', 'interfaces': [], u'hostname': 'nxos-spine1', u'os_version': '7.1(0)D1(1) [build 7.2(0)ZD(0.17)]', u'serial_number': 'TM600C2833B', u'model': 'NX-OSv Chassis', 'vlans': ['1']}
>>>
>>> print(json.dumps(nxs1.facts, indent=4))
{
    "vendor": "cisco",
    "interfaces": [],
    "hostname": "nxos-spine1",
    "os_version": "7.1(0)D1(1) [build 7.2(0)ZD(0.17)]",
    "serial_number": "TM600C2833B",
    "model": "NX-OSv Chassis",
    "vlans": [
        "1"
    ]
}
```

On an IOS device:

```python
>>> csr1 = NTCNAME('csr1')
>>>
>>> print(json.dumps(csr1.facts, indent=4))
{
    "uptime": 87060,
    "vendor": "cisco",
    "uptime_string": "01:00:11:00",
    "interfaces": [
        "GigabitEthernet1",
        "GigabitEthernet2",
        "GigabitEthernet3",
        "GigabitEthernet4",
        "Loopback100"
    ],
    "hostname": "csr1",
    "ios": {
        "config_register": "0x2102"
    },
    "fqdn": "N/A",
    "os_version": "15.5(1)S1",
    "serial_number": "",
    "model": "CSR1000V",
    "vlans": []
}

```

### Sending Show Commands

- `show` method

!!! info
    API enabled devices return JSON by default

```python
>>> nxs1.show('show hostname')
{'hostname': 'nxos-spine1'}
>>>
```

- Use `raw_text=True` to get unstructured data from the device

```python
>>> nxs1.show('show hostname', raw_text=True)
'nxos-spine1 \n'
>>>
```

### Sending Multiple Commands

- `show_list` method

```python
>>> cmds = ['show hostname', 'show run int Eth2/1']

>>> data = nxs1.show_list(cmds, raw_text=True)
```

```python
>>> for d in data:
...   print(d)
...
nxos-spine1

!Command: show running-config interface Ethernet2/1
!Time: Wed Jan  6 18:10:01 2016
version 7.1(0)D1(1)
interface Ethernet2/1
  switchport
  no shutdown
```

### Config Commands

- Use `config` and `config_list`

```python
>>> csr1.config('hostname testname')
>>>
```

```python
>>> csr1.config_list(['interface Gi3', 'shutdown'])
>>>
```

### Viewing Running/Startup Configs

- Use `running_config` and `start_up` device properties
    - Only showing partial config (manually shortened for this slide)

```python
>>> run = csr1.running_config
>>>
>>> print(run)
Building configuration...

Current configuration : 2062 bytes
!
! Last configuration change at 18:26:59 UTC Wed Jan 6 2016 by ntc
!
version 15.5
service timestamps debug datetime msec

lldp run
cdp run
!
ip scp server enable
!
interface GigabitEthernet1
 ip address 10.0.0.50 255.255.255.0
 cdp enable
```

### Copying files

- `file_copy` method

```python
>>> devices = [csr1, nxs1]
>>>
>>> for device in devices:
...   device.file_copy('newconfig.cfg')
...
>>>
```

### Save Configs

- `save` method

`copy run start` for Cisco/Arista and `commit` for Juniper

```python
>>> csr1.save()
True

```

You can also do the equivalent of `copy running-config <filename>` by specifying a filename:

```python
>>> csr1.save('mynewconfig.cfg')
True
```

### Backup Configs

Backup current running configuration and store it locally

```python
>>> csr1.backup_running_config('csr1.cfg')
>>>
```

### Reboot

Reboot target device

Parameters:
  - `timer=0` by default
  - `confirm=False` by default

```python
>>> csr1.reboot(confirm=True)
>>>
```

### Installing Operating Systems

```python
>>> device.install_os('nxos.7.0.3.I2.1.bin')
>>>
```

Full workflow example:

```python
>>> device.file_copy('nxos.7.0.3.I2.1.bin')
>>> device.install_os('nxos.7.0.3.I2.1.bin')
>>> device.save()
>>> device.reboot()          # IF NEEDED, NXOS automatically reboots
>>>
```

#### Cisco IOS Install Mode Option

New in 0.15 there is support for [Install Mode](https://content.cisco.com/chapter.sjs?uri=/searchable/chapter/c/en/us/td/docs/switches/lan/Denali_16-1/ConfigExamples_Technotes/Config_Examples/Misc/qos/m_install_vs_bundle.html.xml) upgrades. To execute this there is an option (defaults to False) to run install mode. **file_copy must be executed before install_os**

```python
device.install_os('cat9k_iosxe.16.12.04.SPA.bin', install_mode=True)
```

Workflow Example

```python
>>> device.file_copy('cat9k_iosxe.16.12.04.SPA.bin')
>>> device.install_os('ncat9k_iosxe.16.12.04.SPA.bin', install_mode=True)  # Reboots device
```
