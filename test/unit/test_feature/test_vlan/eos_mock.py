EOS_SHOW_VLAN = ['show vlan id 10']
EOS_SHOW_VLAN_RESPONSE = [
    {
        "command": "show vlan id 10",
        "result": {
            "sourceDetail": "",
            "vlans": {
                "10": {
                    "status": "active",
                    "interfaces": {},
                    "dynamic": False,
                    "name": "VLAN0010"
                }
            }
        },
        "encoding": "json"
    }
]

EOS_LIST_VLAN = ['show vlan']
EOS_LIST_VLAN_RESPONSE = [
    {
        "command": "show vlan",
        "result": {
            "sourceDetail": "",
            "vlans": {
                "11": {
                    "status": "active",
                    "interfaces": {},
                    "dynamic": False,
                    "name": "pyntc"
                },
                "10": {
                    "status": "active",
                    "interfaces": {},
                    "dynamic": False,
                    "name": "VLAN0010"
                },
                "13": {
                    "status": "active",
                    "interfaces": {},
                    "dynamic": False,
                    "name": "VLAN0013"
                },
                "12": {
                    "status": "active",
                    "interfaces": {},
                    "dynamic": False,
                    "name": "VLAN0012"
                },
                "20": {
                    "status": "active",
                    "interfaces": {},
                    "dynamic": False,
                    "name": "VLAN0020"
                },
                "30": {
                    "status": "active",
                    "interfaces": {},
                    "dynamic": False,
                    "name": "VLAN0030"
                },
                "1": {
                    "status": "active",
                    "interfaces": {
                        "Ethernet8": {
                            "privatePromoted": False
                        },
                        "Ethernet2": {
                            "privatePromoted": False
                        },
                        "Ethernet3": {
                            "privatePromoted": False
                        },
                        "Ethernet1": {
                            "privatePromoted": False
                        },
                        "Ethernet6": {
                            "privatePromoted": False
                        },
                        "Ethernet7": {
                            "privatePromoted": False
                        },
                        "Ethernet5": {
                            "privatePromoted": False
                        }
                    },
                    "dynamic": False,
                    "name": "default"
                }
            }
        },
        "encoding": "json"
    }
]

EOS_CONFIG_VLAN = ['vlan 10', 'name test']
EOS_CONFIG_VLAN_RESPONSE = [{}, {}]

class FakeEOSNative:
    def enable(self, commands, encoding='json'):
        if commands == EOS_SHOW_VLAN:
            return EOS_SHOW_VLAN_RESPONSE
        if commands == EOS_LIST_VLAN:
            return EOS_LIST_VLAN_RESPONSE

        assert False

    def config(self, commands):
        if commands == EOS_CONFIG_VLAN
            return EOS_CONFIG_VLAN_RESPONSE

        assert False

def instance():
    return FakeEOSNative()

