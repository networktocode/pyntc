BASIC_FACTS_KEY_MAP = {
    u'os_version': u'kickstart_ver_str',
    u'model': u'chassis_id',
    u'hostname': u'host_name',
    u'serial_number': u'proc_board_id'
}

UPTIME_KEY_MAP = {
    u'up_days': u'kern_uptm_days',
    u'up_hours': u'kern_uptm_hrs',
    u'up_mins': u'kern_uptm_mins',
    u'up_secs': u'kern_uptm_secs'
}

INTERFACE_KEY_MAP = {
    u'description': u'name',
}


VLAN_KEY_MAP = {
    'id': 'vlanshowbr-vlanid-utf',
    'name': 'vlanshowbr-vlanname',
    'state': 'vlanshowbr-vlanstate',
    'admin_state': 'vlanshowbr-shutstate',
}