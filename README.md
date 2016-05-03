[![Build Status](https://travis-ci.org/networktocode/pyntc.svg?branch=master)](https://travis-ci.org/networktocode/pyntc) [![Coverage Status](https://coveralls.io/repos/github/networktocode/pyntc/badge.svg?branch=master)](https://coveralls.io/github/networktocode/pyntc?branch=master)

# pyntc

- Open source multi-vendor Python library
- Freely provided to the open source community

**The purposes of the library are the following:**

- Successfully establish a common framework for working with different API & device types (including IOS devices)
- Simplify the execution of common tasks including
  - Executing commands
  - Copying files
  - Upgrading devices
  - Rebooting devices
  - Saving / Backing Up Configs



# Supported Platforms

* Cisco IOS platforms
* Cisco NX-OS
* Arista EOS
* Juniper Junos



# Installing pyntc

- Option 1:
  - `sudo pip install ntc` or `pip install ntc --upgrade)`
- Option 2:
  - `git clone https://github.com/networktocode/pyntc.git`
  - `cd pyntc`
  - `sudo python setup.py install`


# Getting Started with pyntc - Option 1

**Using the `ntc_device` object** and supplying all parameters within your code

Step 1. Import Device Object

```
>>> from pyntc import ntc_device as NTC
>>> 
```

Step 2. Create Device Object(s)
  * Key parameter is `device_type`

```
>>> # CREATE DEVICE OBJECT FOR AN IOS DEVICE
>>> 
>>> csr1 = NTC(host='csr1', username='ntc', password='ntc123', device_type='cisco_ios_ssh')
>>>
```

```
>>> # CREATE DEVICE OBJECT FOR A NEXUS DEVICE
>>> 
>>> nxs1 = NTC(host='nxos-spine1', username='ntc', password='ntc123', device_type='cisco_nxos_nxapi')
>>> 
```

# pyntc Configration File


- Simplify creating device objects
- filename:  `.ntc.conf`
- Priority:
  - `filename` param in `ntc_device_by_name()` 
  - Environment Variable = `PYNTC_CONF`
  - Home directory (`.ntc.conf`)
- Specific device_type and a name 
- host is not required if the name is the device's FQDN
- Four supported device types: `cisco_nxos_nxapi`, `cisco_ios_ssh`, `arista_eos_eapi`, and `juniper_junos_netconf`

```bash
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


```
>>> csr1 = NTCNAME('csr1')
>>>
>>> nxs1 = NTCNAME('nxos-spine1')
>>> 
>>> vmx1 = NTCNAME('vmx1')
```


# Getting Started with pyntc - Option 2

**Using the `ntc_device_by_name` object** and the `.ntc.conf` file

Step 1. Import Device Object

```
>>> from pyntc import ntc_device_by_name as NTCNAME
>>> 
```

Step 2. Create Device Object(s)
  * No need to specify credentials, etc. when using `ntc_device_by_name` and the conf file

```
>>> # CREATE DEVICE OBJECT FOR AN IOS DEVICE
>>> 
>>> rtr = NTCNAME('csr1')
>>> 
```

```
>>> # CREATE DEVICE OBJECT FOR A NEXUS DEVICE
>>> 
>>> nxs1 = NTCNAME('nxos-spine1')
>>> 
```

# Gathering Facts

- Use `facts` device property

On a Nexus device:

```
>>> nxs1.facts
{'vendor': 'cisco', 'interfaces': [], u'hostname': 'nxos-spine1', u'os_version': '7.1(0)D1(1) [build 7.2(0)ZD(0.17)]', u'serial_number': 'TM600C2833B', u'model': 'NX-OSv Chassis', 'vlans': ['1']}
>>> 
>>> print json.dumps(nxs1.facts, indent=4)
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

# Gathering Facts (cont'd)

- Use `facts` device property

On an IOS device:

```
>>> print json.dumps(csr1.facts, indent=4)
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

# Sending Show Commands

- `show` method
- API enabled devices return JSON by default

```
>>> nxs1.show('show hostname')
{'hostname': 'nxos-spine1'}
>>>
```

```
>>> nxs1.show('show hostname', raw_text=True)
'nxos-spine1 \n'
>>> 
```

- Use `raw_text=True` to get unstructured data from the device


```
>>> nxs1.show('show version')
{'kern_uptm_secs': 42, 'kick_file_name': 'bootflash:///titanium-d1-kickstart.7.2.0.ZD.0.17.bin', 'loader_ver_str': 'N/A', 'module_id': 'NX-OSv Supervisor Module', 'kick_tmstmp': '11/08/2014 04:03:27', 'isan_file_name': 'bootflash:///titanium-d1.7.2.0.ZD.0.17.bin', 'sys_ver_str': '7.1(0)D1(1) [build 7.2(0)ZD(0.17)]', 'bootflash_size': 1582402, 'kickstart_ver_str': '7.1(0)D1(1) [build 7.2(0)ZD(0.17)]', 'kick_cmpl_time': ' 11/7/2014 18:00:00', 'chassis_id': 'NX-OSv Chassis', 'proc_board_id': 'TM600C2833B', 'memory': 2042024, 'kern_uptm_mins': 17, 'cpu_name': 'Intel(R) Xeon(R) CPU @ 2.50G', 'kern_uptm_hrs': 2, 'isan_tmstmp': '11/08/2014 11:54:08', 'manufacturer': 'Cisco Systems, Inc.', 'header_str': 'Cisco Nexus Operating System (NX-OS) Software\nTAC support: http://www.cisco.com/tac\nDocuments: http://www.cisco.com/en/US/products/ps9372/tsd_products_support_series_home.html\nCopyright (c) 2002-2014, Cisco Systems, Inc. All rights reserved.\nThe copyrights to certain works contained herein are owned by\nother third parties and are used and distributed under license.\nSome parts of this software are covered under the GNU Public\nLicense. A copy of the license is available at\nhttp://www.gnu.org/licenses/gpl.html.\nTitanium is a demo version of the Nexus Operating System\n', 'isan_cmpl_time': ' 11/7/2014 18:00:00', 'host_name': 'nxos-spine1', 'mem_type': 'kB', 'kern_uptm_days': 1}
>>> 
```



```
>>> print nxs1.show('show version', raw_text=True)
Cisco Nexus Operating System (NX-OS) Software
TAC support: http://www.cisco.com/tac
Documents: http://www.cisco.com/en/US/products/ps9372/tsd_products_support_series_home.html
Copyright (c) 2002-2014, Cisco Systems, Inc. All rights reserved.
The copyrights to certain works contained herein are owned by
http://www.gnu.org/licenses/gpl.html.
Titanium is a demo version of the Nexus Operating System
Software
  loader:    version N/A
  kickstart: version 7.1(0)D1(1) [build 7.2(0)ZD(0.17)]
  system:    version 7.1(0)D1(1) [build 7.2(0)ZD(0.17)]
  kickstart image file is: bootflash:///titanium-d1-kickstart.7.2.0.ZD.0.17.bin
  kickstart compile time:  11/7/2014 18:00:00 [11/08/2014 04:03:27]
  system image file is:    bootflash:///titanium-d1.7.2.0.ZD.0.17.bin
  system compile time:     11/7/2014 18:00:00 [11/08/2014 11:54:08]
Hardware
  cisco NX-OSv Chassis ("NX-OSv Supervisor Module")
  Intel(R) Xeon(R) CPU @ 2.50G with 2042024 kB of memory.
  Processor Board ID TM600C2833B
  Device name: nxos-spine1
  bootflash:    1582402 kB
Kernel uptime is 1 day(s), 2 hour(s), 21 minute(s), 3 second(s)
plugin
  Core Plugin, Ethernet Plugin


```

# Sending Multiple Commands

- `show_list` method

```
>>> cmds = ['show hostname', 'show run int Eth2/1']

>>> data = nxs1.show_list(cmds, raw_text=True)
```

```
>>> print data
['nxos-spine1 \n', '!Command: show running-config interface Ethernet2/1\n!Time: Wed Jan  6 18:10:01 2016\nversion 7.1(0)D1(1)\ninterface Ethernet2/1\n  switchport\n  no shutdown\n']
```

```
>>> for d in data:
...   print d
... 
nxos-spine1 

!Command: show running-config interface Ethernet2/1
!Time: Wed Jan  6 18:10:01 2016
version 7.1(0)D1(1)
interface Ethernet2/1
  switchport
  no shutdown
```

# Config Commands

- Use `config` and `config_list`

```
>>> csr1.config('hostname testname')
>>> 
```

Verification

```
>>> print csr1.show('show run | inc hostname')
hostname testname
testname#
>>>
```


```
>>> csr1.config_list(['interface Gi3', 'shutdown'])
>>> 
```

# Viewing Running/Startup Configs

- Use `running_config` and `start_up` device properties
  - Only showing partial config (manually shortened for this slide)

```
>>> run = csr1.running_config
>>> 
>>> print run
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

# Copying files

- `file_copy` method

```
>>> devices = [csr1, nxs1]
>>> 
>>> for device in devices:
...   device.file_copy('newconfig.cfg')
...
>>>
```

# Save Configs

- `save` method

`copy run start` for Cisco/Arista and `commit` for Juniper

```
>>> csr1.save()
True

```

`copy running-config <filename>`

```
>>> csr1.save('mynewconfig.cfg')
True
```

# Backup Configs

Backup current running configuration and store it locally

```
>>> csr1.backup_running_config('csr1.cfg')
>>> 
```

# Reboot

Reboot target device

Parameters:
  - `timer=0` by default
  - `confirm=False` by default

```
>>> csr1.reboot(confirm=True)
>>> 
```

# Installing Operating Systems

Backup current running configuration and store it locally

Note: not currently supported on Juniper

```
>>> device.install_os('nxos.7.0.3.I2.1.bin')
>>> 
```

Full workflow example:

```
>>> device.file_copy('nxos.7.0.3.I2.1.bin')
>>> device.install_os('nxos.7.0.3.I2.1.bin')
>>> device.save()
>>> device.reboot()          # IF NEEDED
>>> 
```

# Summary

- pyntc is a multi-vendor library that currently supports system level tasks
- *getters* coming in the future
- Feature level tasks coming in the future






