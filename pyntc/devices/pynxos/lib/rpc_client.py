import json
from builtins import range

import requests
from requests.auth import HTTPBasicAuth

from pyntc.devices.pynxos.errors import NXOSError


class RPCClient(object):
    def __init__(self, host, username, password, transport="http", port=None, verify=True):
        if transport not in ["http", "https"]:
            raise NXOSError("'%s' is an invalid transport." % transport)

        if port is None:
            if transport == "http":
                port = 80
            elif transport == "https":
                port = 443

        self.url = "%s://%s:%s/ins" % (transport, host, port)
        self.headers = {"content-type": "application/json-rpc"}
        self.username = username
        self.password = password
        self.verify = verify

    def _build_payload(self, commands, method, rpc_version="2.0"):
        payload_list = []

        id_num = 1
        for command in commands:
            payload = dict(
                jsonrpc=rpc_version,
                method=method,
                params=dict(cmd=command, version=1),
                id=id_num,
            )

            payload_list.append(payload)
            id_num += 1

        return payload_list

    def send_request(self, commands, method="cli", timeout=30):
        timeout = int(timeout)
        payload_list = self._build_payload(commands, method)
        response = requests.post(
            self.url,
            timeout=timeout,
            data=json.dumps(payload_list),
            headers=self.headers,
            auth=HTTPBasicAuth(self.username, self.password),
            verify=self.verify,
        )

        response_list = json.loads(response.text)

        if isinstance(response_list, dict):
            response_list = [response_list]

        for i in range(len(commands)):
            response_list[i]["command"] = commands[i]

        return response_list
