import signal
import re
from .lib.rpc_client import RPCClient
from .lib import convert_dict_by_key, converted_list_from_table, strip_unicode
from .lib.data_model import key_maps
from pyntc.devices.pynxos.features.file_copy import FileCopy
from pyntc.devices.pynxos.features.vlans import Vlans
from pyntc.devices.pynxos.errors import CLIError, NXOSError


class RebootSignal(NXOSError):
    pass


class Device(object):
    def __init__(self, host, username, password, transport="http", port=None, timeout=30, verify=True):
        self.host = host
        self.username = username
        self.password = password
        self.transport = transport
        self.timeout = timeout
        self.verify = verify

        self.rpc = RPCClient(host, username, password, transport=transport, port=port, verify=self.verify)

    def _cli_error_check(self, command_response):
        error = command_response.get("error")
        if error:
            command = command_response.get("command")
            if "data" in error:
                raise CLIError(command, error["data"]["msg"])
            else:
                raise CLIError(command, "Invalid command.")

    def _cli_command(self, commands, method="cli"):
        if not isinstance(commands, list):
            commands = [commands]

        rpc_response = self.rpc.send_request(commands, method=method, timeout=self.timeout)

        text_response_list = []
        for command_response in rpc_response:
            self._cli_error_check(command_response)
            text_response_list.append(command_response["result"])

        return strip_unicode(text_response_list)

    def show(self, command, raw_text=False):
        """Send a non-configuration command.

        Args:
            command (str): The command to send to the device.

        Keyword Args:
            raw_text (bool): Whether to return raw text or structured data.

        Returns:
            The output of the show command, which could be raw text or structured data.
        """
        commands = [command]
        list_result = self.show_list(commands, raw_text)
        if list_result:
            return list_result[0]
        else:
            return {}

    def show_list(self, commands, raw_text=False):
        """Send a list of non-configuration commands.

        Args:
            commands (list): A list of commands to send to the device.

        Keyword Args:
            raw_text (bool): Whether to return raw text or structured data.

        Returns:
            A list of outputs for each show command
        """
        return_list = []
        if raw_text:
            response_list = self._cli_command(commands, method="cli_ascii")
            for response in response_list:
                if response:
                    return_list.append(response["msg"])
        else:
            response_list = self._cli_command(commands)
            for response in response_list:
                if response:
                    return_list.append(response["body"])

        return return_list

    def config(self, command):
        """Send a configuration command.

        Args:
            command (str): The command to send to the device.

        Raises:
            CLIError: If there is a problem with the supplied command.
        """
        commands = [command]
        list_result = self.config_list(commands)
        return list_result[0]

    def config_list(self, commands):
        """Send a list of configuration commands.

        Args:
            commands (list): A list of commands to send to the device.

        Raises:
            CLIError: If there is a problem with one of the commands in the list.
        """
        return self._cli_command(commands)

    def save(self, filename="startup-config"):
        """Save a device's running configuration.

        Args:
            filename (str): The filename on the remote device.
                If none is supplied, the implementing class should
                save to the "startup configuration".
        """
        try:
            self.show("copy run %s" % filename, raw_text=True)
        except CLIError as e:
            if "overwrite" in e.message:
                return False
            raise

        return True

    def file_copy_remote_exists(self, src, dest=None, file_system="bootflash:"):
        """Check if a remote file exists. A remote file exists if it has the same name
        as supplied dest, and the same md5 hash as the source.

        Args:
            src (str): Path to local file to check.

        Keyword Args:
            dest (str): The destination file path to be saved on remote the remote device.
                If none is supplied, the implementing class should use the basename
                of the source path.
            file_system (str): The file system for the
                remote file. Defaults to 'bootflash:'.

        Returns:
            True if the remote file exists, False if it doesn't.
        """
        fc = FileCopy(self, src, dst=dest, file_system=file_system)
        if fc.file_already_exists():
            return True
        return False

    def file_copy(self, src, dest=None, file_system="bootflash:"):
        """Send a local file to the device.

        Args:
            src (str): Path to the local file to send.

        Keyword Args:
            dest (str): The destination file path to be saved on remote flash.
                If none is supplied, the implementing class should use the basename
                of the source path.
            file_system (str): The file system for the
                remote fle. Defaults to bootflash:'.
        """
        fc = FileCopy(self, src, dst=dest, file_system=file_system)
        fc.send()

    def _disable_confirmation(self):
        self.show("terminal dont-ask")

    def reboot(self, confirm=False):
        """Reboot the device.

        Args:
            confirm(bool): if False, this method has no effect.
        """
        if confirm:

            def handler(signum, frame):
                raise RebootSignal("Interupting after reload")

            signal.signal(signal.SIGALRM, handler)
            signal.alarm(5)

            try:
                self._disable_confirmation()
                self.show("reload")
            except RebootSignal:
                signal.alarm(0)

            signal.alarm(0)
        else:
            print("Need to confirm reboot with confirm=True")

    def set_boot_options(self, image_name, kickstart=None, reboot=True):
        """Set boot variables
        like system image and kickstart image.

        Args:
            The main system image file name.

        Keyword Args: many implementors may choose
            to supply a kickstart parameter to specicify a kickstart image.
        """
        self._disable_confirmation()
        if reboot:
            reboot_arg = ""
        else:
            reboot_arg = " no-reload"
        try:
            if kickstart is None:
                self.show("install all nxos %s%s" % (image_name, reboot_arg), raw_text=True)
            else:
                self.show("install all system %s kickstart %s%s" % (image_name, kickstart, reboot_arg), raw_text=True)
        except CLIError:
            pass

    def get_boot_options(self):
        """Get current boot variables
        like system image and kickstart image.

        Returns:
            A dictionary, e.g. { 'kick': router_kick.img, 'sys': 'router_sys.img'}
        """
        boot_options_raw_text = self.show("show boot", raw_text=True).split("Boot Variables on next reload")[1]
        if "kickstart" in boot_options_raw_text:
            kick_regex = r"kickstart variable = bootflash:/(\S+)"
            sys_regex = r"system variable = bootflash:/(\S+)"

            kick = re.search(kick_regex, boot_options_raw_text).group(1)
            sys = re.search(sys_regex, boot_options_raw_text).group(1)
            retdict = dict(kick=kick, sys=sys)
        else:
            nxos_regex = r"NXOS variable = bootflash:/(\S+)"
            nxos = re.search(nxos_regex, boot_options_raw_text).group(1)
            retdict = dict(sys=nxos)

        install_status = self.show("show install all status", raw_text=True)
        retdict["status"] = install_status

        return retdict

    def rollback(self, filename):
        """Rollback to a checkpoint file.

        Args:
            filename (str): The filename of the checkpoint file to load into the running configuration.
        """
        self.show("rollback running-config file %s" % filename, raw_text=True)

    def checkpoint(self, filename):
        """Save a checkpoint of the running configuration to the device.

        Args:
            filename (str): The filename to save the checkpoint as on the remote device.
        """
        self.show_list(["terminal dont-ask", "checkpoint file %s" % filename], raw_text=True)

    def backup_running_config(self, filename):
        """Save a local copy of the running config.

        Args:
            filename (str): The local file path on which to save the running config.
        """
        with open(filename, "w") as f:
            f.write(self.running_config)

    @property
    def running_config(self):
        """Return the running configuration of the device."""
        response = self.show("show running-config", raw_text=True)
        return response

    def _convert_uptime_to_string(self, up_days, up_hours, up_mins, up_secs):
        return "%02d:%02d:%02d:%02d" % (up_days, up_hours, up_mins, up_secs)

    def _convert_uptime_to_seconds(self, up_days, up_hours, up_mins, up_secs):
        seconds = up_days * 24 * 60 * 60
        seconds += up_hours * 60 * 60
        seconds += up_mins * 60
        seconds += up_secs

        return seconds

    def _get_interface_detailed_list(self):
        try:
            interface_table = self.show("show interface status")
            interface_list = converted_list_from_table(
                interface_table, "interface", key_maps.INTERFACE_KEY_MAP, fill_in=True
            )
        except CLIError:
            return []

        return interface_list

    def _get_interface_list(self):
        iface_detailed_list = self._get_interface_detailed_list()
        iface_list = list(x["interface"] for x in iface_detailed_list)

        return iface_list

    def _get_vlan_list(self):
        vlans = Vlans(self)
        vlan_list = vlans.get_list()

        return vlan_list

    def _get_show_version_facts(self):
        show_version_result = self.show("show version")
        uptime_facts = convert_dict_by_key(show_version_result, key_maps.UPTIME_KEY_MAP)

        up_days = uptime_facts["up_days"]
        up_hours = uptime_facts["up_hours"]
        up_mins = uptime_facts["up_mins"]
        up_secs = uptime_facts["up_secs"]

        uptime_string = self._convert_uptime_to_string(up_days, up_hours, up_mins, up_secs)
        uptime_seconds = self._convert_uptime_to_seconds(up_days, up_hours, up_mins, up_secs)

        show_version_facts = convert_dict_by_key(show_version_result, key_maps.BASIC_FACTS_KEY_MAP)

        show_version_facts["uptime"] = uptime_seconds
        show_version_facts["uptime_string"] = uptime_string

        return show_version_facts

    @property
    def facts(self):
        """Return a dictionary of facts about the device.

        The dictionary must include the following keys.
        All keys are strings, the value type is given in parenthesis:
            uptime (int)
            vendor (str)
            os_version (str)
            interfaces (list of strings)
            hostname (str)
            fqdn (str)
            uptime_string (str)
            serial_number (str)
            model (str)
            vlans (list of strings)

        The dictionary can also include a vendor-specific dictionary, with the
        device type as a key in the outer dictionary.

        Example:
            {
                "uptime": 1819711,
                "vendor": "cisco",
                "os_version": "7.0(3)I2(1)",
                "interfaces": [
                    "mgmt0",
                    "Ethernet1/1",
                    "Ethernet1/2",
                    "Ethernet1/3",
                    "Ethernet1/4",
                    "Ethernet1/5",
                    "Ethernet1/6",
                ],
                "hostname": "n9k1",
                "fqdn": "N/A",
                "uptime_string": "21:01:28:31",
                "serial_number": "SAL1819S6LU",
                "model": "Nexus9000 C9396PX Chassis",
                "vlans": [
                    "1",
                    "2",
                    "3",
                ]
            }
        """
        if hasattr(self, "_facts"):
            return self._facts

        facts = {}

        show_version_facts = self._get_show_version_facts()
        facts.update(show_version_facts)

        iface_list = self._get_interface_list()
        facts["interfaces"] = iface_list

        vlan_list = self._get_vlan_list()
        facts["vlans"] = vlan_list

        facts["fqdn"] = "N/A"

        self._facts = facts
        return facts


#    def feature(self, feature_name):
#        try:
#            feature_module = importlib.import_module(
#                'pynxos.features.%s' % (feature_name))
#            return feature_module.instance(self)
#        except ImportError:
#            raise FeatureNotFoundError(feature_name, self.device_type)
