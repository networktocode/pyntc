"""Module for using an F5 TMOS device over the REST / SOAP.
"""

import hashlib
import os
import re
import time

import bigsuds
import requests
from f5.bigip import ManagementRoot

from .base_device import BaseDevice

F5_API_DEVICE_TYPE = 'f5_tmos_icontrol'


class F5Device(BaseDevice):
    def __init__(self, host, username, password, **kwargs):
        super(F5Device, self).__init__(host, username, password, vendor='f5',
                                       device_type=F5_API_DEVICE_TYPE)

        self.vendor = 'F5 Networks'

        self.hostname = host
        self.username = username
        self.password = password
        self.api_handler = ManagementRoot(self.hostname, self.username,
                                          self.password)

        self._open_soap()

    def _open_soap(self):
        try:
            self.soap_handler = bigsuds.BIGIP(hostname=self.hostname,
                                              username=self.username,
                                              password=self.password)
            self.devices = self.soap_handler.Management.Device.get_list()
        except bigsuds.OperationFailed as err:
            raise RuntimeError('ConfigSync API Error ({})'.format(err))

    def _reconnect(self):
        """ Reconnects to the device

        """
        self.api_handler = ManagementRoot(self.hostname, self.username,
                                          self.password)

    def _get_free_space(self):
        """Gets free space on the device

        Example of 'vgdisplay -s --units G' command:

        [root@ntc:Active:Standalone] config # vgdisplay -s --units G
        "vg-db-sda" 30.98 GB  [23.89 GB  used / 7.10 GB free]

        Returns:
            int - number of gigabytes of free space
        """
        free_space = None
        free_space_output = self.api_handler.tm.util.bash.exec_cmd('run',
                                                                   utilCmdArgs='-c "vgdisplay -s --units G"')
        if free_space_output:
            free_space = free_space_output.commandResult
            free_space_regex = '.*\s\/\s(\d+\.?\d+) GB free'
            match = re.match(free_space_regex, free_space)

            if match:
                free_space = float(match.group(1))

        return free_space

    def _check_free_space(self, min_space=0):
        """Checks for minimum space on the device

        Returns:
            bool - True / False if min_space is available on the device
        """
        free_space = self._get_free_space()

        if not free_space:
            raise ValueError('Could not get free space')
        elif free_space >= min_space:
            return True
        elif free_space < min_space:
            return False

    def _file_copy_remote_md5(self, filepath):
        """Gets md5 checksum of the filename

        Example of 'md5sum' command:

        [root@ntc:Active:Standalone] config # md5sum /tmp/systemauth.pl
        c813ac405cab73591492db326ad8893a  /tmp/systemauth.pl

        Returns:
            str - md5sum of the filename
        """
        md5sum_result = None
        md5sum_output = self.api_handler.tm.util.bash.exec_cmd('run',
                                                               utilCmdArgs='-c "md5sum {}"'.format(
                                                                   filepath))
        if md5sum_output:
            md5sum_result = md5sum_output.commandResult
            md5sum_result = md5sum_result.split()[0]

        return md5sum_result

    @staticmethod
    def _file_copy_local_file_exists(filepath):
        return os.path.isfile(filepath)

    def _file_copy_local_md5(self, filepath, blocksize=2 ** 20):
        """Gets md5 checksum from the filepath

        Returns:
            str - if the file exists
            None - if the file does not exist
        """
        if self._file_copy_local_file_exists(filepath):
            m = hashlib.md5()
            with open(filepath, "rb") as f:
                buf = f.read(blocksize)
                while buf:
                    m.update(buf)
                    buf = f.read(blocksize)
            return m.hexdigest()

    def _check_md5sum(self, filename, checksum):
        """Checks if md5sum is correct

        Returns:
            bool - True / False if checksums match
        """
        md5sum = self._file_copy_remote_md5(filename)

        if checksum == md5sum:
            return True
        else:
            return False

    def _image_exists(self, image_name):
        """Checks if image exists on the device

        Returns:
            bool - True / False if image exists
        """
        all_images_output = self.api_handler.tm.util.unix_ls.exec_cmd('run',
                                                                      utilCmdArgs="/shared/images")

        if all_images_output:
            all_images = all_images_output.commandResult.splitlines()
        else:
            return None

        if image_name in all_images:
            return True
        else:
            return False

    def _volume_exists(self, volume_name):
        """Checks if volume exists on the device

        Returns:
            bool - True / False if volume exists
        """
        result = self.api_handler.tm.sys.software.volumes.volume.exists(
            name=volume_name)

        return result

    def _get_active_volume(self):
        """Gets name of active volume on the device

        Returns:
            str - name of active volume
        """
        volumes = self._get_volumes()
        for _volume in volumes:
            if hasattr(_volume, 'active') and _volume.active is True:
                current_volume = _volume.name
                return current_volume

    def _get_volumes(self):
        """Gets list of volumes on the device

        Returns:
            list - of volumes
        """
        volumes = self.api_handler.tm.sys.software.volumes.get_collection()

        return volumes

    def _get_images(self):
        """Gets list of images on the device

        Returns:
            list - of images
        """
        images = self.api_handler.tm.sys.software.images.get_collection()

        return images

    def _image_install(self, image_name, volume):
        """Requests the installation of the image on a volume

        Returns:
            None
        """
        options = []

        create_volume = not self._volume_exists(volume)

        if create_volume:
            options.append({'create-volume': True})

        self.api_handler.tm.sys.software.images.exec_cmd('install',
                                                         name=image_name,
                                                         volume=volume,
                                                         options=options)

    def image_installed(self, image_name, volume):
        """Checks if image is installed on a specified volume

        Returns:
            bool - True / False if image installed on a specified volume
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
                if _volume.name == volume and _volume.version == image.version and _volume.basebuild == image.build and _volume.status == 'complete':
                    return True

        return False

    def _wait_for_image_installed(self, image_name, volume, timeout=900):
        """Waits for the device to install image on a volume

        Returns:
            bool - True / False if installation has been successful
        """
        end_time = time.time() + timeout

        while time.time() < end_time:
            time.sleep(20)
            if self.image_installed(image_name=image_name, volume=volume):
                return True

        return False

    def _image_match(self, image_name, checksum):
        """Checks if image name matches the checksum

        Returns:
            bool - True / False if image matches the checksum
        """
        if self._image_exists(image_name):
            image = os.path.join('/shared/images', image_name)
            if self._check_md5sum(image, checksum):
                return True

        return False

    def _reboot_to_volume(self, volume_name=None):
        """Requests the reboot (activiation) to a specified volume

        Returns:
            None
        """
        if volume_name:
            self.api_handler.tm.sys.software.volumes.exec_cmd('reboot',
                                                              volume=volume_name)
        else:
            # F5 SDK API does not support reboot to the current volume.
            # This is a workaround by issuing reboot command from bash directly.
            self.api_handler.tm.util.bash.exec_cmd('run',
                                                   utilCmdArgs='-c "reboot"')

    def _wait_for_device_reboot(self, volume_name, timeout=600):
        """Waits for the device to be booted into a specified volume

        Returns:
            bool - True / False if reboot has been successful
        """
        end_time = time.time() + timeout

        time.sleep(60)

        while time.time() < end_time:
            time.sleep(5)
            try:
                self._reconnect()
                volume = self.api_handler.tm.sys.software.volumes.volume.load(
                    name=volume_name)
                if hasattr(volume, 'active') and volume.active is True:
                    return True
            except Exception:
                pass
        return False

    def _upload_image(self, image_filepath):
        """Uploads an iso image to the device

        Returns:
            None
        """
        image_filename = os.path.basename(image_filepath)
        _URI = 'https://{hostname}/mgmt/cm/autodeploy/software-image-uploads/{filename}'.format(
            hostname=self.hostname, filename=image_filename)
        chunk_size = 512 * 1024
        size = os.path.getsize(image_filepath)
        headers = {'Content-Type': 'application/octet-stream'}
        requests.packages.urllib3.disable_warnings()
        start = 0

        with open(image_filepath, 'rb') as fileobj:
            while True:
                payload = fileobj.read(chunk_size)
                if not payload:
                    break

                end = fileobj.tell()

                if end < chunk_size:
                    end = size
                content_range = "{}-{}/{}".format(start, end - 1, size)
                headers['Content-Range'] = content_range
                resp = requests.post(_URI, auth=(self.username, self.password),
                                     data=payload, headers=headers,
                                     verify=False)

                start += len(payload)

    def open(self):
        pass

    def close(self):
        pass

    def config(self, command):
        raise NotImplementedError

    def config_list(self, commands):
        raise NotImplementedError

    def show(self, command, raw_text=False):
        raise NotImplementedError

    def show_list(self, commands, raw_text=False):
        raise NotImplementedError

    def save(self, filename=None):
        raise NotImplementedError

    def file_copy(self, src, dest=None, **kwargs):
        if dest and not dest.startswith("/shared/images"):
            raise NotImplementedError(
                "Support only for images - destination is always /shared/images")

        self._upload_image(image_filepath=src)

    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        if dest and not dest.startswith("/shared/images"):
            raise NotImplementedError(
                "Support only for images - destination is always /shared/images")

        local_md5sum = self._file_copy_local_md5(filepath=src)
        file_basename = os.path.basename(src)

        if not self._image_match(image_name=file_basename,
                                 checksum=local_md5sum):
            return False
        else:
            return True

    def reboot(self, timer=0, confirm=False, volume=None):
        if confirm:
            if self._get_active_volume() == volume:
                volume_name = None
            else:
                volume_name = volume

            self._reboot_to_volume(volume_name=volume_name)

            if not self._wait_for_device_reboot(volume_name=volume):
                raise RuntimeError("Reboot to volume {} failed".format(volume))
        else:
            print('Need to confirm reboot with confirm=True')

    def get_boot_options(self):
        active_volume = self._get_active_volume()

        return {'active_volume': active_volume}

    def set_boot_options(self, image_name, **vendor_specifics):
        volume = vendor_specifics.get('volume')

        free_space = self._check_free_space(min_space=6)

        if not free_space:
            raise RuntimeError(
                "Not enough free space to install OS".format(volume))

        self._image_install(image_name=image_name, volume=volume)

        if not self._wait_for_image_installed(image_name=image_name,
                                              volume=volume):
            raise RuntimeError("Installation of {} failed".format(volume))

    def checkpoint(self, filename):
        raise NotImplementedError

    def rollback(self, checkpoint_file):
        raise NotImplementedError

    def backup_running_config(self, filename):
        raise NotImplementedError

    def _get_uptime(self):
        return self.soap_handler.System.SystemInfo.get_uptime()

    def _get_version(self):
        return self.soap_handler.System.SystemInfo.get_version()

    def _get_serial_number(self):
        system_information = self.soap_handler.System.SystemInfo.get_system_information()
        chassis_serial = system_information.get('chassis_serial')

        return chassis_serial

    def _get_model(self):
        return self.soap_handler.System.SystemInfo.get_marketing_name()

    def _get_hostname(self):
        return self.soap_handler.Management.Device.get_hostname(self.devices)[0]

    def _get_interfaces_list(self):
        interfaces = self.soap_handler.Networking.Interfaces.get_list()
        return interfaces

    def _get_vlans(self):
        rd_list = self.soap_handler.Networking.RouteDomainV2.get_list()
        rd_vlan_list = self.soap_handler.Networking.RouteDomainV2.get_vlan(
            rd_list)

        return rd_vlan_list

    @staticmethod
    def _uptime_to_string(uptime):
        days = uptime / (24 * 60 * 60)
        uptime = uptime % (24 * 60 * 60)
        hours = uptime / (60 * 60)
        uptime = uptime % (60 * 60)
        mins = uptime / 60
        uptime = uptime % 60
        seconds = uptime

        return '%02d:%02d:%02d:%02d' % (days, hours, mins, seconds)

    @property
    def facts(self):
        facts = {
            'uptime': self._get_uptime(),
            'vendor': self.vendor,
            'model': self._get_model(),
            'hostname': self._get_hostname(),
            'fqdn': self._get_hostname(),
            'os_version': self._get_version(),
            'serial_number': self._get_serial_number(),
            'interfaces': self._get_interfaces_list(),
            'vlans': self._get_vlans(),
            'uptime_string': self._uptime_to_string(self._get_uptime()),
        }

        return facts

    def running_config(self):
        raise NotImplementedError

    def startup_config(self):
        raise NotImplementedError
