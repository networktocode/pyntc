# Introduction

pyntc is an open source multi-vendor Python library that establishes a common framework for working with different network APIs & device types (including IOS devices)

It's main purpose is to simplify the execution of common tasks including:
  - Executing commands
  - Copying files
  - Upgrading devices
  - Rebooting devices
  - Saving / Backing Up Configs

# Supported Platforms

* Cisco AireOS - uses netmiko (SSH)
* Cisco ASA - uses netmiko (SSH)
* Cisco IOS platforms - uses netmiko (SSH)
* Cisco NX-OS - uses pynxos (NX-API)
* Arista EOS - uses pyeapi (eAPI)
* Juniper Junos - uses PyEz (NETCONF)
* F5 Networks - uses f5-sdk (ReST)

# Installing pyntc

Option 1:

```
"pip install pyntc" or "pip install pyntc --upgrade"
```

Option 2:

```
git clone https://github.com/networktocode/pyntc.git
cd pyntc
pip install poetry
poetry install
```


# Getting Started with pyntc

There are two ways to get started with pyntc.

The first way is to use the `ntc_device` object. Just pass in all required parameters to the object to initialize your device.  Here we are showing the import, but renaming the object to `NTC`.

```
>>> from pyntc import ntc_device as NTC
>>>
```

Like many libraries, we need to pass in the host/IP and credentials.  Because this is a multi-vendor/API library, we also use the `device_type` parameter to identify which device we are building an instance of.

pyntc currently supports four device types:
* cisco_aireos_ssh
* cisco_asa_ssh
* cisco_ios_ssh
* cisco_nxos_nxapi
* arista_eos_eapi
* juniper_junos_netconf
* f5_tmos_icontrol

The example below shows how to build a device object when working with a Cisco IOS router.

```
>>> # CREATE DEVICE OBJECT FOR AN IOS DEVICE
>>>
>>> csr1 = NTC(host='csr1', username='ntc', password='ntc123', device_type='cisco_ios_ssh')
>>>
```

And here is an object for a Cisco Nexus device:

```
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

We can now build device objects just by referencing the name of the device from the conf file.

```
>>> from pyntc import ntc_device_by_name as NTCNAME
>>>
>>> csr1 = NTCNAME('csr1')
>>>
>>> nxs1 = NTCNAME('nxos-spine1')
>>>
>>> vmx1 = NTCNAME('vmx1')
```


Once the device object is creating using either `ntc_device` or `ntc_device_by_name`, you can start using the built-in device methods in pyntc.

Note: the only method and property not supported on all devices is `install_os`.  It is not supported on Juniper Junos devices.

### Gathering Facts

- Use `facts` device property

On a Nexus device:

```
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

```
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
- Note: API enabled devices return JSON by default

```
>>> nxs1.show('show hostname')
{'hostname': 'nxos-spine1'}
>>>
```

- Use `raw_text=True` to get unstructured data from the device

```
>>> nxs1.show('show hostname', raw_text=True)
'nxos-spine1 \n'
>>>
```

### Sending Multiple Commands

- `show_list` method

```
>>> cmds = ['show hostname', 'show run int Eth2/1']

>>> data = nxs1.show_list(cmds, raw_text=True)
```

```
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

```
>>> csr1.config('hostname testname')
>>>
```

```
>>> csr1.config_list(['interface Gi3', 'shutdown'])
>>>
```

### Viewing Running/Startup Configs

- Use `running_config` and `start_up` device properties
  - Only showing partial config (manually shortened for this slide)

```
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

```
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

```
>>> csr1.save()
True

```

You can also do the equivalent of `copy running-config <filename>` by specifying a filename:

```
>>> csr1.save('mynewconfig.cfg')
True
```

### Backup Configs

Backup current running configuration and store it locally

```
>>> csr1.backup_running_config('csr1.cfg')
>>>
```

### Reboot

Reboot target device

Parameters:
  - `timer=0` by default
  - `confirm=False` by default

```
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

## Contributing

This section describes how to install *pyntc* for development, how to run
tests, and make sure you are a good contributor.

### Branches

<!-- TODO: Correct/complete documentation. -->

- `main` - Reserved for released code
- `develop` - Work in progress on the main roadmap
- `<feature>` - Individual feature branches, should be PR'd to `develop`.

### Installing dependencies for local development

This repository uses [poetry](https://python-poetry.org/) for dependency
management.

For best results, you should use
[virtualenv](https://virtualenv.pypa.io/en/latest/) and
[virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/en/latest/), which
can both be installed to your system packages using `pip install virtualenv
virtualenvwrapper`.

You'll also need Python 3.6+ as your interpreter. See the *virtualenv*
documentation on choosing the correct Python interpretery binary if your system
provides multiple versions.

Follow these steps to set up your local development environment:

```bash
# Make a new virtualenv named "pyntc" and activate it
$ mkvirtualenv pyntc
# Double check your version
$ python --version
Python 3.7.7
# Install poetry
$ pip install poetry
# Install project dependencies as well as development dependencies
$ poetry install
```

In addition to *poetry*, you may want to install *tox* which is a test
environment controller and runner.

```bash
# Make sure you're in the "pyntc" virtualenv, skip this step if you already are
$ workon pyntc
# Install tox
$ pip install tox
```

### Running tests locally

The easiest way to run tests locally is to directly invoke the
[unittest](https://docs.python.org/3/library/unittest.html) module directly.

Test modules are located in `./test/unit/` and fixtures in `./test/fixtures/`.

```bash
# Run all tests locally
$ python -m unittest discover ./test/unit
```

It's also possible to run local tests using *tox* if you have it installed.
This will create separate virtualenvs for each Python version in the `tox.ini`
configuration, and download all dependencies separately.

```bash
# Run all tests against multiple Python versions
$ tox
```

---


### Local Doc Build

If you want to build the documentation locally, follow these steps:

1. Run poetry to install all necessary packages: 

```bash
$ poetry install
$ poetry shell
```

2. Create local docs:

```bash
$ sphinx-build -vvv -b html ./docs public
``

3. Run a local python server to check your documentation rendering:

```bash
cd public
python -m http.server &
```


[![Build Status](https://travis-ci.org/networktocode/pyntc.svg?branch=main)](https://travis-ci.org/networktocode/pyntc)
[![Coverage Status](https://coveralls.io/repos/github/networktocode/pyntc/badge.svg?branch=main)](https://coveralls.io/github/networktocode/pyntc?branch=main)
