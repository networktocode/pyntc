import os
import json

CURRNENT_DIR = os.path.dirname(os.path.realpath(__file__))

def _load_json_from_path(path):
    with open(path, 'r') as f:
        return json.load(f)

def get(vlan_id):
    path = os.path.join(CURRNENT_DIR, 'get', vlan_id)
    if not os.path.isfile(path):
        return None

    return _load_json_from_path(path)

def getall():
    path = os.path.join(CURRNENT_DIR, 'getall')
    return _load_json_from_path(path)
