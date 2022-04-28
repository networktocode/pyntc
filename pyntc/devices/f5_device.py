"""Module for using an F5 TMOS device over the REST / SOAP."""

import hashlib
import os
import re
import time
import warnings

import requests
from f5.bigip import ManagementRoot

from pyntc.errors import OSInstallError, FileTransferError, NTCFileNotFoundError, NotEnoughFreeSpaceError
from .base_device import BaseDevice


class F5Device(BaseDevice):
    """F5 LTM Device Implementation."""

    vendor = "f5"

    def __init__(self, host, username, password, **kwargs):  # noqa:  D403
        """PyNTC implementation for F5 device.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
        """
        super().__init__(host, username, password, device_type="f5_tmos_icontrol")

        self.api_handler = ManagementRoot(self.host, self.username, self.password)

    def _check_free_space(self, min_space=0):
        """Check for minimum space on the device.

        Args:
            min_space (int): The minimal amount of space required.

        Raises:
            NotEnoughFreeSpaceError: When the amount of space on the device is less than min_space.
        """
        free_space = self._get_free_space()

        if not free_space:
            raise ValueError("Could not get free space")
        elif free_space >= min_space:
            return
        elif free_space < min_space:
            raise NotEnoughFreeSpaceError(hostname=self.host, min_space=min_space)

    def _check_md5sum(self, filename, checksum):
        """Check is md5sum is correct.

        Args:
            filename (str): Name of file to generate md5.
            checksum (str): checksum used against image.

        Returns:
            bool: True if md5 matches. Otherwise, false.
        """
        md5sum = self._file_copy_remote_md5(filename)

        if checksum == md5sum:
            return True
        else:
            return False

    @staticmethod
    def _file_copy_local_file_exists(filepath):
        return os.path.isfile(filepath)

    def _file_copy_local_md5(self, filepath, blocksize=2**20):
        if self._file_copy_local_file_exists(filepath):
            m = hashlib.md5()  # nosec
            with open(filepath, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    def _file_copy_remote_md5(self, filepath):
        md5sum_result = None
        md5sum_output = self.api_handler.tm.util.bash.exec_cmd("run", utilCmdArgs='-c "md5sum {}"'.format(filepath))
        if md5sum_output:
            md5sum_result = md5sum_output.commandResult
            md5sum_result = md5sum_result.split()[0]

        return md5sum_result

    def _get_active_volume(self):
        """Get name of active volume on the device.

        Returns:
            str: Name of active volume.
        """
        volumes = self._get_volumes()
        for _volume in volumes:
            if hasattr(_volume, "active") and _volume.active is True:
                current_volume = _volume.name
                return current_volume

    def _get_free_space(self):
        """Get free space on the device.

        Example:
            >>> [root@ntc:Active:Standalone] config # vgdisplay -s --units G
            >>> "vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]

        Returns:
            int: Number of gigabytes of free space.
        """
        free_space = None
        free_space_output = self.api_handler.tm.util.bash.exec_cmd("run", utilCmdArgs='-c "vgdisplay -s --units G"')
        if free_space_output:
            free_space = free_space_output.commandResult
            free_space_regex = r".*\s\/\s(\d+\.?\d+) GB free"
            match = re.match(free_space_regex, free_space)

            if match:
                free_space = float(match.group(1))

        return free_space

    def _get_images(self):
        images = self.api_handler.tm.sys.software.images.get_collection()

        return images

    def _get_interfaces_list(self):
        interfaces = self.soap_handler.Networking.Interfaces.get_list()
        return interfaces

    def _get_model(self):
        return self.soap_handler.System.SystemInfo.get_marketing_name()

    def _get_serial_number(self):
        system_information = self.soap_handler.System.SystemInfo.get_system_information()
        chassis_serial = system_information.get("chassis_serial")

        return chassis_serial

    def _get_uptime(self):
        return self.soap_handler.System.SystemInfo.get_uptime()

    def _get_version(self):
        return self.soap_handler.System.SystemInfo.get_version()

    def _get_vlans(self):
        rd_list = self.soap_handler.Networking.RouteDomainV2.get_list()
        rd_vlan_list = self.soap_handler.Networking.RouteDomainV2.get_vlan(rd_list)

        return rd_vlan_list

    def _get_volumes(self):
        volumes = self.api_handler.tm.sys.software.volumes.get_collection()

        return volumes

    def _image_booted(self, image_name, **vendor_specifics):
        """Check if requested booted volume is an active volume.

        Args:
            image_name (str): Name of image.

        Returns:
            bool: True if booted volume is equal to active volume. Otherwise, false.
        """
        volume = vendor_specifics.get("volume")
        return True if self._get_active_volume() == volume else False

    def _image_exists(self, image_name):
        """Check if image exists on the device.

        Args:
            image_name (str): Name of image.

        Returns:
            bool: True if image exists on device. Otherwise, false.
        """
        all_images_output = self.api_handler.tm.util.unix_ls.exec_cmd("run", utilCmdArgs="/shared/images")

        if all_images_output:
            all_images = all_images_output.commandResult.splitlines()
        else:
            return None

        if image_name in all_images:
            return True
        else:
            return False

    def _image_install(self, image_name, volume):
        """Request installation of the image on a volume.

        Args:
            image_name (str): Name of volume.
            volume (str): Name of volume to install image on.
        """
        options = []

        create_volume = not self._volume_exists(volume)

        if create_volume:
            options.append({"create-volume": True})

        self.api_handler.tm.sys.software.images.exec_cmd("install", name=image_name, volume=volume, options=options)

    def _image_match(self, image_name, checksum):
        """Check if image name matches the checksum.

        Args:
            image_name (str): Name of image.
            checksum (str): Expected checksum.

        Returns:
            bool: True if expected checksum matches file checksum. Otherwise, false.
        """
        if self._image_exists(image_name):
            image = os.path.join("/shared/images", image_name)
            if self._check_md5sum(image, checksum):
                return True

        return False

    def _reboot_to_volume(self, volume_name=None):
        """Request the reboot (activation) to a specified volume.

        Args:
            volume_name (str, optional): Volume name. Defaults to None.
        """
        if volume_name:
            self.api_handler.tm.sys.software.volumes.exec_cmd("reboot", volume=volume_name)
        else:
            # F5 SDK API does not support reboot to the current volume.
            # This is a workaround by issuing reboot command from bash directly.
            self.api_handler.tm.util.bash.exec_cmd("run", utilCmdArgs='-c "reboot"')

    def _reconnect(self):
        """Reconnect to the device."""
        self.api_handler = ManagementRoot(self.host, self.username, self.password)

    def _upload_image(self, image_filepath):
        """Upload an iso image to the device.

        Args:
            image_filepath (str): Name of file.
        """
        image_filename = os.path.basename(image_filepath)
        _URI = "https://{hostname}/mgmt/cm/autodeploy/software-image-uploads/{filename}".format(
            hostname=self.host, filename=image_filename
        )
        chunk_size = 512 * 1024
        size = os.path.getsize(image_filepath)
        headers = {"Content-Type": "application/octet-stream"}
        requests.packages.urllib3.disable_warnings()
        start = 0

        with open(image_filepath, "rb") as fileobj:
            while True:
                payload = fileobj.read(chunk_size)
                if not payload:
                    break

                end = fileobj.tell()
                if end < chunk_size:
                    end = size
                content_range = "{}-{}/{}".format(start, end - 1, size)
                headers["Content-Range"] = content_range
                requests.post(
                    _URI, auth=(self.username, self.password), data=payload, headers=headers, verify=False  # nosec
                )

                start += len(payload)

    @staticmethod
    def _uptime_to_string(uptime):
        """Change uptime to a string.

        Args:
            uptime (float): Uptime represented in a float.

        Returns:
            str: Uptime in a string.
        """
        days = uptime / (24 * 60 * 60)
        uptime = uptime % (24 * 60 * 60)
        hours = uptime / (60 * 60)
        uptime = uptime % (60 * 60)
        mins = uptime / 60
        uptime = uptime % 60
        seconds = uptime

        return "%02d:%02d:%02d:%02d" % (days, hours, mins, seconds)

    def _volume_exists(self, volume_name):
        """Check if volume exist.

        Args:
            volume_name (str): Volume name.

        Returns:
            bool: True if volume exists. Otherwise, false.
        """
        result = self.api_handler.tm.sys.software.volumes.volume.exists(name=volume_name)

        return result

    def _wait_for_device_reboot(self, volume_name, timeout=600):
        """Wait for device to be booted into a specified volume.

        Args:
            volume_name (str): Volume name to boot into.
            timeout (int, optional): Timeout value. Defaults to 600.

        Returns:
            bool: True if device boots into specified voluem successfully. Otherwise, false.
        """
        end_time = time.time() + timeout
        time.sleep(60)

        while time.time() < end_time:
            time.sleep(5)
            try:
                self._reconnect()
                volume = self.api_handler.tm.sys.software.volumes.volume.load(name=volume_name)
                if hasattr(volume, "active") and volume.active is True:
                    return True
            except Exception:  # noqa E722 # nosec
                pass
        return False

    def _wait_for_image_installed(self, image_name, volume, timeout=1800):
        """Wait for the device to install image on a volume.

        Args:
            image_name (str): The name of the image that should be booting.
            volume (str): The volume that the device should be booting into.
            timeout (int): The number of seconds to wait for device to boot up.

        Raises:
            OSInstallError: When the volume is not booted before the timeout is reached.
        """
        end_time = time.time() + timeout

        while time.time() < end_time:
            time.sleep(20)
            # Avoid race-conditions issues. Newly created volumes _might_ lack
            # of .version attribute in first seconds of their live.
            try:
                if self.image_installed(image_name=image_name, volume=volume):
                    return
            except:  # noqa E722 # nosec
                pass

        raise OSInstallError(hostname=self.hostname, desired_boot=volume)

    def backup_running_config(self, filename):
        """Backup running configuration.

        Args:
            filename (str): Name of file to save running config to.

        Raises:
            NotImplementedError: Function currently not implemeneted.
        """
        raise NotImplementedError

    @property
    def boot_options(self):
        """Get active volume.

        Returns:
            dict: Key is ``active volume`` with value being the current active volume.
        """
        active_volume = self._get_active_volume()

        return {"active_volume": active_volume}

    def checkpoint(self, filename):
        """Create checkpoint configuration file.

        Args:
            filename (str): Name of file to save running config to.

        Raises:
            NotImplementedError: Function currently not implemeneted.
        """
        raise NotImplementedError

    def close(self):
        """Implement ``pass``."""
        pass

    def config(self, command):
        """Send command to device.

        Args:
            command (str): Command.

        Raises:
            NotImplementedError: Function currently not implemented.
        """
        raise NotImplementedError

    @property
    def uptime(self):
        """Get uptime of device in seconds.

        Returns:
            float: Uptime of device.
        """
        if self._uptime is None:
            self._uptime = self._get_uptime()

        return self._uptime

    @property
    def uptime_string(self):
        """
        Get uptime of device in format dd:hh:mm:ss.

        Returns:
            str: Uptime of device.
        """
        if self._uptime_string is None:
            self._uptime_string = self._uptime_to_string(self._get_uptime())

        return self._uptime_string

    @property
    def hostname(self):
        """Get hostname of device.

        Returns:
            str: Hostname.
        """
        if self._hostname is None:
            fqdn_split = self.fqdn.split(".")
            self._hostname = fqdn_split[0]

        return self._hostname

    @property
    def interfaces(self):
        """Get list of images on the device.

        Returns:
            list: List of images.
        """
        if self._interfaces is None:
            self._interfaces = self._get_interfaces_list()

        return self._interfaces

    @property
    def vlans(self):
        """Get list of vlans on device.

        Returns:
            list: List of vlans.
        """
        if self._vlans is None:
            self._vlans = self._get_vlans()

        return self._vlans

    @property
    def fqdn(self):
        """Get fully-qualified domain name.

        Returns:
            str: Fully qualified domain name.
        """
        if self._fqdn is None:
            settings = self.api_handler.tm.sys.global_settings.load()
            self._fqdn = settings.hostname

        return self._fqdn

    @property
    def model(self):
        """Get model of device.

        Returns:
            str: Model of device.
        """
        if self._model is None:
            self._model = self._get_model()

        return self._model

    @property
    def os_version(self):
        """Get version of device.

        Returns:
            str: Version on device.
        """
        if self._os_version is None:
            self._os_version = self._get_version()

        return self._os_version

    @property
    def serial_number(self):
        """Get serial number of device.

        Returns:
            str: Serial number of device.
        """
        if self._serial_number is None:
            self._serial_number = self._get_serial_number()

        return self._serial_number

    def file_copy(self, src, dest=None, **kwargs):
        """Copy file to device.

        Args:
            src (str): Source of file.
            dest (str, optional): Destination to save file. Defaults to None.

        Raises:
            FileTransferError: Error in verifying if file existed before transfer.
        """
        if not self.file_copy_remote_exists(src, dest, **kwargs):
            self._check_free_space(min_space=6)
            self._upload_image(image_filepath=src)
            if not self.file_copy_remote_exists(src, dest, **kwargs):
                raise FileTransferError(
                    message="Attempted file copy, but could not validate file existed after transfer"
                )

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        """Copy file to device.

        Args:
            src (str): Source of file.
            dest (str, optional): Destination to save file. Defaults to None.

        Raises:
            NotImplementedError: Destination must be ``/shared/images``.

        Returns:
            bool: True if image specified exists on device. Otherwise, false.
        """
        if dest and not dest.startswith("/shared/images"):
            raise NotImplementedError("Support only for images - destination is always /shared/images")

        local_md5sum = self._file_copy_local_md5(filepath=src)
        file_basename = os.path.basename(src)

        if not self._image_match(image_name=file_basename, checksum=local_md5sum):
            return False
        else:
            return True

    def image_installed(self, image_name, volume):
        """Check if image is installed on specified volume.

        Args:
            image_name (str): Name of image.
            volume (str): Volume to look for image on.

        Raises:
            RuntimeError: Either image name or volume were not specified.

        Returns:
            bool: True if file exists on volume. Otherwise, false.
        """
        if not image_name or not volume:
            raise RuntimeError("image_name and volume must be specified")

        image = None
        images_on_device = self._get_images()

        for _image in images_on_device:
            # fullPath = u'BIGIP-11.6.0.0.0.401.iso'
            if _image.fullPath == image_name:
                image = _image

        if image:
            volumes = self._get_volumes()

            for _volume in volumes:
                if (
                    _volume.name == volume
                    and _volume.version == image.version  # noqa W503
                    and _volume.basebuild == image.build  # noqa W503
                    and _volume.status == "complete"  # noqa W503
                ):
                    return True

        return False

    def install_os(self, image_name, **vendor_specifics):
        """Install OS on device.

        Args:
            image_name (str): Image name.

        Raises:
            NTCFileNotFoundError: Error is image is not found on device.

        Returns:
            bool: True if image is installed successfully. Otherwise, false.
        """
        volume = vendor_specifics.get("volume")
        if not self.image_installed(image_name, volume):
            self._check_free_space(min_space=6)
            if not self._image_exists(image_name):
                raise NTCFileNotFoundError(hostname=self.hostname, file=image_name, dir="/shared/images")
            self._image_install(image_name=image_name, volume=volume)
            self._wait_for_image_installed(image_name=image_name, volume=volume)

            return True

        return False

    def open(self):
        """Implement ``pass``."""
        pass

    def reboot(self, timer=0, volume=None, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            timer (int, optional): The time to wait before reloading. Defaults to 0.
            volume (str, optional): Active volume to reboot. Defaults to None.

        Raises:
            RuntimeError: If device is unreachable after timeout period, raise an error.

        Example:
            >>> device = F5Device(**connection_args)
            >>> device.reboot()
            >>>
        """
        if kwargs.get("confirm"):
            warnings.warn("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        if self._get_active_volume() == volume:
            volume_name = None
        else:
            volume_name = volume

        self._reboot_to_volume(volume_name=volume_name)

        if not self._wait_for_device_reboot(volume_name=volume):
            raise RuntimeError("Reboot to volume {} failed".format(volume))

    def rollback(self, checkpoint_file):
        """Rollback to checkpoint configurtion file.

        Args:
            checkpoint_file (str): Name of checkpoint file.

        Raises:
            NotImplementedError: Function currently not implemented.
        """
        raise NotImplementedError

    def running_config(self):
        """Get running configuration.

        Raises:
            NotImplementedError: Function currently not implemented.
        """
        raise NotImplementedError

    def save(self, filename=None):
        """Save running configuration.

        Args:
            filename (str, optional): Name of file to save running configuration to. Defaults to None.

        Raises:
            NotImplementedError: Function currently not implemented.
        """
        raise NotImplementedError

    def set_boot_options(self, image_name, **vendor_specifics):
        """Set boot option on device.

        Args:
            image_name (str): Name of image.

        Raises:
            NTCFileNotFoundError: Error if file is not found on device.
        """
        volume = vendor_specifics.get("volume")
        self._check_free_space(min_space=6)
        if not self._image_exists(image_name):
            raise NTCFileNotFoundError(hostname=self.hostname, file=image_name, dir="/shared/images")
        self._image_install(image_name=image_name, volume=volume)
        self._wait_for_image_installed(image_name=image_name, volume=volume)

    def show(self, command, raw_text=False):
        """Run cli command on device.

        Args:
            command (str): Command to be ran.
            raw_text (bool, optional): Specifies if you want raw text. Defaults to False.

        Raises:
            NotImplementedError: [description]
        """
        raise NotImplementedError

    def startup_config(self):
        """Get startup configuration.

        Raises:
            NotImplementedError: Function currently not implemented.
        """
        raise NotImplementedError
