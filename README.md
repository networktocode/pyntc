[![Build Status](https://travis-ci.org/networktocode/pyntc.svg?branch=master)](https://travis-ci.org/networktocode/pyntc) [![Coverage Status](https://coveralls.io/repos/github/networktocode/pyntc/badge.svg?branch=master)](https://coveralls.io/github/networktocode/pyntc?branch=master)

# Introduction
This Python library was built for as a multi-vendor abstraction for interacting with network devices 

## Vendor Support
- Cisco IOS = cisco_ios_ssh
- Cisco NXOS = cisco_ns_nxapi
- Arista EOS = arista_eos_eapi
- Juniper JUNOS = juniper_junos_netconf

## Install
To install the package and all of it's depedencies:
```
pip install pyntc
```
## Config File
Configure your .ntc.conf file, as shown in the example below in your current directory. The "host" value can include either and IP or FQDN. 
```
[<cisco_ios_ssh|cisco_nxos_nxapi|arista_eos_eapi|juniper_junos_netconf>:<name>]
host: <dns_or_ip>
username: <username>
password: <password>
transport <http|https|ssh>p
```

E.g. 
```

[arista_eos_eapi:eos-spine1]
host: eos-spine1.ntc.com
username: ntc
password: ntc123
transport: http

[arista_eos_eapi:eos-spine2]
host: 10.1.1.1
username: ntc
password: ntc123
transport: http

[arista_eos_eapi:eos-leaf1]
host: eos-leaf1
username: ntc
password: ntc123
transport: http

[arista_eos_eapi:eos-leaf2]
host: eos-leaf2
username: ntc
password: ntc123
transport: http


[cisco_nxos_nxapi:nxos-spine1]
host: nxos-spine1
username: ntc
password: ntc123
transport: http

[cisco_nxos_nxapi:nxos-spine2]
host: nxos-spine2
username: ntc
password: ntc123
transport: http

[cisco_nxos_nxapi:nxos-leaf1]
host: nxos-leaf1
username: ntc
password: ntc123
transport: http

[cisco_nxos_nxapi:nxos-leaf2]
host: nxos-leaf2
username: ntc
password: ntc123
transport: http

[cisco_ios_ssh:csr1]
host: csr1
username: ntc
password: ntc123
port: 22

[cisco_ios_ssh:csr2]
host: csr2
username: ntc
password: ntc123
port: 22

[cisco_ios_ssh:csr3]
host: csr3
username: ntc
password: ntc123
port: 22

[juniper_junos_netconf:junos1]
host: junos1
username: ntc
password: ntc123
port: 22

[juniper_junos_netconf:junos2]
host: junos2
username: ntc
password: ntc123
port: 22
```
## Test in python

Ensuring you are in the same directoy as the .net.conf file, you can test:
Import Library, taking in devices from the .net.conf file as NTCNAME is this scenario
```
Python 2.7.11+ (default, Apr 17 2016, 14:00:29) 
[GCC 5.3.1 20160413] on linux2
Type "help", "copyright", "credits" or "license" for more information.
>>> 
>>> from pyntc import ntc_device_by_name as NTCNAME
>>> 
```
Assign devices to python usable variables, and into a list
 
#### Cisco IOS usage 

```
>>> r1 = NTCNAME('csr1')
>>> r3 = NTCNAME('csr3')
>>> 
>>> csr_devices = [r1, r3]
>>>  
>>>  
```
Open the connection, and grab some data. The following attributes are predefined: facts, running_config and startup_config

Configs ommitted for brevity sake
```
... for csr in csr_devices:
...     csr.open()
... 
>>> 
>>> import json
>>> print json.dumps(r1.facts,indent=4)
{
    "uptime": 7380, 
    "vendor": "cisco", 
    "uptime_string": "00:02:03:00", 
    "interfaces": [
        "GigabitEthernet1", 
        "GigabitEthernet2", 
        "GigabitEthernet3", 
        "GigabitEthernet4"
    ], 
    "hostname": "csr1", 
    "fqdn": "N/A", 
    "cisco_ios_ssh": {
        "config_register": "0x2102"
    }, 
    "os_version": "15.5(3)S2", 
    "serial_number": "", 
    "model": "CSR1000V", 
    "vlans": []
}
>>> print r1.running_config
Building configuration...

Current configuration : 1744 bytes
!
! Last configuration change at 19:56:01 UTC Tue May 3 2016
!
version 15.5
service timestamps debug datetime msec
service timestamps log datetime msec
no platform punt-keepalive disable-kernel-core
platform console virtual
!
hostname csr1
----ommitted-----
line vty 2 4
 privilege level 15
 login local
 transport input ssh
!
!
end

>>> print r1.startup_config
Using 1745 out of 33554432 bytes
!
! Last configuration change at 00:38:38 UTC Thu Apr 21 2016
!
version 15.5
service timestamps debug datetime msec
service timestamps log datetime msec
no platform punt-keepalive disable-kernel-core
platform console virtual
!
hostname csr1
----ommitted-----
line vty 2 4
 privilege level 15
 login local
 transport input ssh
!
!
end
```
#### Arista EOS usage 
 
```

>>> 
>>> s1 = NTCNAME('eos-leaf1')
>>> s2 = NTCNAME('eos-leaf2')
>>> 
>>> eos_devices = [s1, s2]
>>> 
>>> for eos in eos_devices:
...     eos.open()
... 
>>> print json.dumps(s1.facts,indent=4)
{
    "uptime": 7558, 
    "vendor": "arista", 
    "os_version": "4.15.5M-3054042.4155M", 
    "interfaces": [
        "Ethernet1", 
        "Ethernet2", 
        "Ethernet3", 
        "Ethernet4", 
        "Ethernet5", 
        "Ethernet6", 
        "Ethernet7", 
        "Management1"
    ], 
    "hostname": "eos-leaf1", 
    "fqdn": "eos-leaf1.ntc.com", 
    "uptime_string": "00:02:05:58", 
    "serial_number": "", 
    "model": "vEOS", 
    "vlans": [
        "1"
    ]
}

```
#### Cisco NXOS usage 

 
```
>>> 
>>> nx1 = NTCNAME('nxos-spine1')
>>> nx2 = NTCNAME('nxos-spine2')
>>> 
>>> nxos_devices = [nx1, nx2]
>>> 
>>> for nxos in nxos_devices:
...     nxos.open()
... 
>>> print json.dumps(nx1.facts,indent=4)
{
    "uptime": 7585, 
    "vendor": "cisco", 
    "os_version": "7.3(1)D1(1) [build 7.3(1)D1(0.10)]", 
    "interfaces": [
        "mgmt0", 
        "Ethernet2/1", 
----ommitted-----
        "Ethernet4/48", 
        "Vlan1"
    ], 
    "hostname": "nxos-spine1", 
    "fqdn": "N/A", 
    "uptime_string": "00:02:06:25", 
    "serial_number": "TM29D1D533B", 
    "model": "NX-OSv Chassis", 
    "vlans": [
        "1"
    ]
}
>>> 
``` 

## Standard Methods
The following defined methods provide standard functions: backup_running_config, file_copy, save, reboot. 

```
>>>r1.backup_running_config('backups/csr1.cfg')
>>>r1.file_copy('cisco-ios-fake-image.bin')
>>>r1.save()
True
>>>r1.reboot(confirm=True)
```

There are four methods that can be used to send commands directly to the device: show, show_list, config, config_list.

show and show_list can be used to send show commands. show is used to send a single show command and show_list is used to send a list of show commands.

config and config_list can be used to send show commands. config is used to send a single show command and config_list is used to send a list of show commands.

Examples:
```
>>> print r1.show('show ip int brief')
>>>
You should this output:

Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet1       10.0.0.50       YES NVRAM  up                    up      
GigabitEthernet2       10.254.13.1     YES NVRAM  up                    up      
GigabitEthernet3       unassigned      YES NVRAM  administratively down down    
GigabitEthernet4       10.254.12.1     YES NVRAM  up                    up      
Loopback100            1.1.1.1         YES NVRAM  up                    up      
>>> 
```
```
>>> commands = ['show run interface Gi1', 'show run | inc route']
>>> 
>>> output = r1.show_list(commands)
>>> 
>>> for out in output:
...     print out
... 
Building configuration...

Current configuration : 150 bytes
!
interface GigabitEthernet1
 description MANAGEMENT
 vrf forwarding Mgmt-intf
 ip address 10.0.0.50 255.255.255.0
 negotiation auto
 cdp enable
end

router ospf 100
 router-id 1.1.1.1
ip route vrf Mgmt-intf 0.0.0.0 0.0.0.0 10.0.0.2
```






