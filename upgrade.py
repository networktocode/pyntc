import os
import re
import time

from netmiko.cisco import CiscoWlcSSH


RE_FILENAME_FIND_VERSION = re.compile(r"^.+?(?P<version>\d+(?:-|_)\d+(?:-|_)\d+(?:-|_)\d+)\.", re.M)
RE_AP_BOOT_OPTIONS = re.compile(
    r"^(?P<name>.+?)\s+(?P<primary>(?:\d+\.){3}\d+)\s+(?P<backup>(?:\d+\.){3}\d+)\s+(?P<status>\S+).+$",
    re.M,
)
RE_AP_IMAGE_COUNT = re.compile(r"^[Tt]otal\s+number\s+of\s+APs\.+\s+(?P<count>\d+)\s*$", re.M)
RE_AP_IMAGE_DOWNLOADED = re.compile(r"^\s*[Cc]ompleted\s+[Pp]redownloading\.+\s+(?P<downloaded>\d+)\s*$", re.M)
RE_AP_IMAGE_UNSUPPORTED = re.compile(r"^\s*[Nn]ot\s+[Ss]upported\.+\s+(?P<unsupported>\d+)\s*$", re.M)
RE_AP_IMAGE_FAILED = re.compile(r"^\s*[Ff]ailed\s+to\s+[Pp]redownload\.+\s+(?P<failed>\d+)\s*$", re.M)
RE_WLANS = re.compile(
    r"^(?P<wlan_id>\d+)\s+(?P<profile>\S+)\s*/\s+(?P<ssid>\S+)\s+(?P<status>\S+)\s+(?P<interface>.+?)\s*\S+\s*$", re.M
)


class WLCTest:
    def __init__(self, host, username, password):
        self.connection = CiscoWlcSSH(host, username=username, password=password)

    @staticmethod
    def convert_filename_to_version(filename):
        version_match = RE_FILENAME_FIND_VERSION.match(filename)
        version_string = version_match.groupdict()["version"]
        version = re.sub("-|_", ".", version_string)
        return version

    def send_commands(self, commands):
        if isinstance(commands, str):
            commands = [commands]
        responses = []
        for command in commands:
            print(f"Sending command: {command}")
            response = self.connection.send_command(command)
            if "Incorrect usage" in response or "Error:" in response:
                raise ValueError(f"Error sending command '{command}', got response\n\n{response}\n")
            responses.append(response)
        return responses

    @property
    def boot_options(self):
        show_boot_out = self.send_commands("show boot")
        re_primary_path = r"^Primary\s+Boot\s+Image\s*\.+\s*(?P<primary>\S+)(?P<status>.*)$"
        re_backup_path = r"^Backup\s+Boot\s+Image\s*\.+\s*(?P<backup>\S+)(?P<status>.*)$"
        primary = re.search(re_primary_path, show_boot_out[0], re.M)
        backup = re.search(re_backup_path, show_boot_out[0], re.M)
        if primary:
            result = primary.groupdict()
            primary_status = result.pop("status")
            result.update(backup.groupdict())
            backup_status = result.pop("status")
            if "default" in primary_status:
                result["sys"] = result["primary"]
            elif "default" in backup_status:
                result["sys"] = result["backup"]
            else:
                result["sys"] = None
            print(f"Primary image to boot is: {result['primary']}")
            print(f"Secondary image to boot is: {result['backup']}")
            print(f"Default image to boot is: {result['sys']}")
        else:
            result = {"sys": None}
        return result

    def is_image_on_device(self, version, boot_options=None):
        boot_options = boot_options or self.boot_options
        if version in boot_options.values():
            print("Image exists on device")
            return True
        print(f"Image needs to be transferred to device before upgrading")
        return False

    def transfer_file(self, username, password, server, filepath, filename, protocol, delay_factor=20):
        print(f"Starting transfer of {filename} to device")
        if not filepath.endswith("/"):
            filepath = f"{filepath.strip()}/"

        commands = [
            f"transfer download username {username}",
            f"transfer download password {password}",
        ]
        print(f"Setting transfer username and password")
        for command in commands:
            self.connection.send_command(command)

        commands = [
            f"transfer download datatype code",
            f"transfer download mode {protocol}",
            f"transfer download serverip {server}",
            f"transfer download path {filepath}",
            f"transfer download filename {filename}",
        ]
        self.send_commands(commands)

        print("Starting file transfer")
        response = self.connection.send_command_timing("transfer download start")
        if "Are you sure you want to start? (y/N)" in response:
            response = self.connection.send_command("y", auto_find_prompt=False, delay_factor=delay_factor)
        if "File transfer is successful" not in response:
            raise ValueError(message=f"Did not find expected success message in response, found:\n{response}")
        print("Successfully transferred image to device")
        return True

    def set_boot_options(self, version):
        boot_options = self.boot_options
        if not boot_options["sys"] == version:
            if boot_options["primary"] == version:
                boot_command = "boot primary"
            elif boot_options["backup"] == version:
                boot_command = "boot backup"
            else:
                raise ValueError(f"Did not find {version} on device")
            self.send_commands(f"config {boot_command}")
            self.connection.save()
            if not self.boot_options["sys"] == version:
                raise ValueError(f"Unable to set device to boot {version}")
        return True

    @property
    def ap_boot_options(self):
        ap_images = self.send_commands("show ap image all")
        print(f"Access Point images are:\n\n{ap_images[0]}")
        ap_boot_options = RE_AP_BOOT_OPTIONS.finditer(ap_images[0])
        boot_options_by_ap = {
            ap["name"]: {
                "primary": ap.group("primary"),
                "backup": ap.group("backup"),
                "status": ap.group("status").lower(),
            }
            for ap in ap_boot_options
        }
        print(f"AP Boot Options are:\n{boot_options_by_ap}")
        return boot_options_by_ap

    def is_access_point_boot_option_set_to_version(self, version, boot_option, ap_boot_options=None):
        if ap_boot_options is None:
            ap_boot_options = self.ap_boot_options

        if boot_option not in {"primary", "backup"}:
            raise ValueError(f"'boot_option must be either 'primary' or 'backup', found '{boot_option}")

        print(f"Checking if Access Points {boot_option} image is using {version}")
        if all([ap_boot_option[boot_option] == version for ap_boot_option in ap_boot_options.values()]):
            print(f"All Access Points have a {boot_option} image of {version}")
            return True
        return False

    def is_image_on_all_access_points(self, version, ap_boot_options=None):
        print("Collecting Acces Point Boot Options")
        ap_boot_options = ap_boot_options or self.ap_boot_options
        if any([
            self.is_access_point_boot_option_set_to_version(version, boot_option, ap_boot_options)
            for boot_option in ["primary", "backup"]
        ]):
            return True
        return False

    @property
    def ap_image_stats(self):
        print("Collecting AP Image Stats")
        ap_images = self.send_commands("show ap image all")[0]
        count = RE_AP_IMAGE_COUNT.search(ap_images).group(1)
        print(f"Total Access Points is {count}\n")
        downloaded = RE_AP_IMAGE_DOWNLOADED.search(ap_images).group(1)
        print(f"Access Points that have downloaded image is {downloaded}\n")
        unsupported = RE_AP_IMAGE_UNSUPPORTED.search(ap_images).group(1)
        print(f"Access Points that are unsuppored is {unsupported}\n")
        failed = RE_AP_IMAGE_FAILED.search(ap_images).group(1)
        print(f"Access Points that failed to download image is {failed}\n")
        return {
            "count": int(count),
            "downloaded": int(downloaded),
            "unsupported": int(unsupported),
            "failed": int(failed),
        }

    def _wait_for_ap_image_download(self, timeout=3600):
        start = time.time()
        ap_image_stats = self.ap_image_stats
        ap_count = ap_image_stats["count"]
        downloaded = 0
        while downloaded < ap_count:
            ap_image_stats = self.ap_image_stats
            downloaded = ap_image_stats["downloaded"]
            unsupported = ap_image_stats["unsupported"]
            failed = ap_image_stats["failed"]
            if unsupported or failed:
                raise ValueError(
                    f"Failed transferring image to AP\nUnsupported: {unsupported}\nFailed: {failed}\n"
                )
            elapsed_time = time.time() - start
            if elapsed_time > timeout:
                raise ValueError(
                    "Failed waiting for AP image to be transferred to all devices:\n"
                    f"Total: {ap_count}\nDownloaded: {downloaded}"
                )

    def transfer_image_to_access_points(self, version):
        print(f"Checking that image {version} is available on device")
        boot_options = self.boot_options
        if not self.is_image_on_device(version, boot_options):
            raise ValueError(f"Did not find image {version} on device")
        if boot_options["primary"] == version:
            option = "primary"
        else:
            option = "secondary"
        print(f"Downloading {option} image to all Access Points")
        self.send_commands(f"config ap image predownload {option} all")
        self._wait_for_ap_image_download()
        return True

    def set_access_points_primary_boot_image(self, version):
        counter = 0
        while counter < 3 and self.is_access_point_boot_option_set_to_version(version, "backup"):
            counter += 1
            self.send_commands("config ap image swap all")
            # testing showed delay in reflecting changes when issuing `show ap image all`
            time.sleep(2)

        if not self.is_access_point_boot_option_set_to_version(version, "primary"):
            raise ValueError(f"Unable to set all Access Points to use {version}")
        return True


host = "10.130.37.194" # "141.167.113.101"
username = "coneng"
password = "Essat30"
wlc = WLCTest(host, username, password)

# Transfer image
file_transferred = False
filename = "AS_5500_8_5_161_7.aes"
version = wlc.convert_filename_to_version(filename)
image_on_device = wlc.is_image_on_device(version)
if not image_on_device:
    filepath = "WIRELESS/SOFTWARE/"
    file_server = "145.245.165.19"
    file_server_username = "tftp"
    file_server_password = "Flash2012"
    transfer_protocol = "ftp"
    file_transferred = wlc.transfer_file(file_server_username, file_server_password, file_server, filepath, filename, transfer_protocol)

# Set Device to boot image
device_ready_to_boot = False
if image_on_device or file_transferred:
    device_ready_to_boot = wlc.set_boot_options(version)

# Transfer image to Access Points
image_transferred_to_access_points = False
if device_ready_to_boot:
    image_on_all_access_points = wlc.is_image_on_all_access_points(version)
    if not image_on_all_access_points:
        image_transferred_to_access_points = wlc.transfer_image_to_access_points(version)

# Set Access Points to boot image
device_access_points_ready_to_boot = False
if device_ready_to_boot:
    if image_on_all_access_points or image_transferred_to_access_points:
        device_access_points_ready_to_boot = wlc.set_access_points_primary_boot_image(version)

'''
TODO:

* Disable WLANS
* Reboot
* Enable WLANS
* Verify device state
'''
'''
Execute:
$ netmiko wlc upgrade.py
# Displaying netmiko wlc upgrade.py.
'''
