from pynxos.errors import CLIError

GET_VLAN = 'show vlan id 10'
GET_VLAN_RESPONSE = {
                            u'vlanshowrspan-vlantype': u'notrspan',
                            u'TABLE_vlanbriefid': {
                                u'ROW_vlanbriefid': {
                                    u'vlanshowbr-vlanstate': u'active',
                                    u'vlanshowplist-ifidx': u'port-channel10-12,Ethernet1/4-7,Ethernet2/5-6',
                                    u'vlanshowbr-vlanid-utf': u'10',
                                    u'vlanshowbr-vlanname': u'pyntc_baby',
                                    u'vlanshowbr-vlanid': u'10',
                                    u'vlanshowbr-shutstate': u'noshutdown'
                                }
                            },
                            u'TABLE_mtuinfoid': {
                                u'ROW_mtuinfoid': {
                                    u'vlanshowinfo-vlanid': u'10',
                                    u'vlanshowinfo-media-type': u'enet',
                                    u'vlanshowinfo-vlanmode': u'ce-vlan'
                                }
                            },
                            u'is-vtp-manageable': u'enabled'
                        }

LIST_VLAN = 'show vlan'
LIST_VLAN_RESPONSE = {
    "TABLE_mtuinfo": {
        "ROW_mtuinfo": [
            {
                "vlanshowinfo-vlanid": "1",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "2",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "3",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "4",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "5",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "6",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "7",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "8",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "9",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "10",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "11",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "12",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "13",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "14",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "15",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "16",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "17",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "18",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "19",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "20",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "22",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "30",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "40",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "99",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "100",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "101",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "102",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "103",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "104",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "105",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "123",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "200",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            },
            {
                "vlanshowinfo-vlanid": "500",
                "vlanshowinfo-media-type": "enet",
                "vlanshowinfo-vlanmode": "ce-vlan"
            }
        ]
    },
    "TABLE_vlanbrief": {
        "ROW_vlanbrief": [
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "Ethernet1/2-3,Ethernet1/8-9,Ethernet1/11-48,Ethernet2/8-12",
                "vlanshowbr-vlanid-utf": "1",
                "vlanshowbr-vlanname": "default",
                "vlanshowbr-vlanid": "1",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "2",
                "vlanshowbr-vlanname": "VLAN0002",
                "vlanshowbr-vlanid": "2",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "3",
                "vlanshowbr-vlanname": "VLAN0003",
                "vlanshowbr-vlanid": "3",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "4",
                "vlanshowbr-vlanname": "VLAN0004",
                "vlanshowbr-vlanid": "4",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "5",
                "vlanshowbr-vlanname": "VLAN0005",
                "vlanshowbr-vlanid": "5",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "6",
                "vlanshowbr-vlanname": "VLAN0006",
                "vlanshowbr-vlanid": "6",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "7",
                "vlanshowbr-vlanname": "VLAN0007",
                "vlanshowbr-vlanid": "7",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "8",
                "vlanshowbr-vlanname": "VLAN0008",
                "vlanshowbr-vlanid": "8",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "9",
                "vlanshowbr-vlanname": "VLAN0009",
                "vlanshowbr-vlanid": "9",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "10",
                "vlanshowbr-vlanname": "pyntc_baby",
                "vlanshowbr-vlanid": "10",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "11",
                "vlanshowbr-vlanname": "VLAN0011",
                "vlanshowbr-vlanid": "11",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "12",
                "vlanshowbr-vlanname": "VLAN0012",
                "vlanshowbr-vlanid": "12",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "13",
                "vlanshowbr-vlanname": "VLAN0013",
                "vlanshowbr-vlanid": "13",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "14",
                "vlanshowbr-vlanname": "VLAN0014",
                "vlanshowbr-vlanid": "14",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "15",
                "vlanshowbr-vlanname": "VLAN0015",
                "vlanshowbr-vlanid": "15",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "16",
                "vlanshowbr-vlanname": "VLAN0016",
                "vlanshowbr-vlanid": "16",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "17",
                "vlanshowbr-vlanname": "VLAN0017",
                "vlanshowbr-vlanid": "17",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "18",
                "vlanshowbr-vlanname": "VLAN0018",
                "vlanshowbr-vlanid": "18",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "19",
                "vlanshowbr-vlanname": "VLAN0019",
                "vlanshowbr-vlanid": "19",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanstate": "active",
                "vlanshowplist-ifidx": "port-channel10-12,Ethernet1/4-7,Ethernet2/5-6",
                "vlanshowbr-vlanid-utf": "20",
                "vlanshowbr-vlanname": "peer_keepalive",
                "vlanshowbr-vlanid": "20",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "22",
                "vlanshowbr-vlanid-utf": "22",
                "vlanshowbr-vlanname": "VLAN0022",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "30",
                "vlanshowbr-vlanid-utf": "30",
                "vlanshowbr-vlanname": "VLAN0030",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "40",
                "vlanshowbr-vlanid-utf": "40",
                "vlanshowbr-vlanname": "VLAN0040",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "99",
                "vlanshowbr-vlanid-utf": "99",
                "vlanshowbr-vlanname": "native",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "100",
                "vlanshowbr-vlanid-utf": "100",
                "vlanshowbr-vlanname": "VLAN0100",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "101",
                "vlanshowbr-vlanid-utf": "101",
                "vlanshowbr-vlanname": "VLAN0101",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "102",
                "vlanshowbr-vlanid-utf": "102",
                "vlanshowbr-vlanname": "VLAN0102",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "103",
                "vlanshowbr-vlanid-utf": "103",
                "vlanshowbr-vlanname": "VLAN0103",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "104",
                "vlanshowbr-vlanid-utf": "104",
                "vlanshowbr-vlanname": "VLAN0104",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "105",
                "vlanshowbr-vlanid-utf": "105",
                "vlanshowbr-vlanname": "VLAN0105",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "123",
                "vlanshowbr-vlanid-utf": "123",
                "vlanshowbr-vlanname": "VLAN0123",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "200",
                "vlanshowbr-vlanid-utf": "200",
                "vlanshowbr-vlanname": "VLAN0200",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            },
            {
                "vlanshowbr-vlanid": "500",
                "vlanshowbr-vlanid-utf": "500",
                "vlanshowbr-vlanname": "VLAN0500",
                "vlanshowbr-vlanstate": "active",
                "vlanshowbr-shutstate": "noshutdown"
            }
        ]
    }
}

CONFIG_VLAN = ['vlan 10', 'name test']
CONFIG_VLAN_RESPONSE = [None, None]

GET_BAD = 'show vlan 5000'

CONFIG_BAD = ['vlan 5000']

CONFIG_WITH_NAME = ['vlan 10', 'name test']
CONFIG_WITH_NAME_RESPONSE = [None, None]


class FakeNXOSNative:
    def show(self, command, raw_text=False):
        if command == NXOS_GET_VLAN:
            return NXOS_GET_VLAN_RESPONSE
        if command == NXOS_LIST_VLAN:
            return NXOS_LIST_VLAN_RESPONSE
        if command == GET_BAD:
            raise CLIError


        assert False

    def config_list(self, commands):
        if commands == CONFIG_VLAN:
            return NXOS_CONFIG_VLAN_RESPONSE
        if commands == CONFIG_BAD:
            raise CLIError
        if commands == CONFIG_WITH_NAME:
            CONFIG_WITH_NAME_RESPONSE

        assert False

def instance():
    return FakeNXOSNative()
