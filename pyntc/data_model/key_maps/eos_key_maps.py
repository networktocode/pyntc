# Key maps for EOS devices are stored here.

BASIC_FACTS_KM = {
    'model': 'modelName',
    'os_version': 'internalVersion',
    'serial_number': 'serialNumber'
}


INTERFACES_KM = {
    'speed': 'bandwidth',
    'duplex': 'duplex',
    'vlan': ['vlanInformation', 'vlanId'],
    'state': 'linkStatus',
    'description': 'description',
}

VLAN_KM = {
    'state': 'state',
    'name': 'name',
    'id': 'vlan_id',
}
