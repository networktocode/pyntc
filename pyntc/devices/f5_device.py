"""Module for using an F5 TMOS device over the REST.
"""

import os
import re
import time

import requests
from f5.bigip import ManagementRoot

from .base_device import BaseDevice

F5_API_DEVICE_TYPE = 'f5_tmos_rest'


class F5Device(BaseDevice):

    def __init__(self, host, username, password, **kwargs):
        super(F5Device, self).__init__(host, username, password, vendor='f5',
                                       device_type=F5_API_DEVICE_TYPE)

        self.hostname = hostname
        self.username = username
        self.password = password
        self.api_handler = ManagementRoot(self.hostname, self.username,
                                          self.password)

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
        elif min_space < free_space:
            return False
        elif min_space >= free_space:
            return True

    def _get_md5sum(self, filename):
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
                                                                   filename))
        if md5sum_output:
            md5sum_result = md5sum_output.commandResult
            md5sum_result = md5sum_result.split()[0]

        return md5sum_result

    def _check_md5sum(self, filename, checksum):
        """Checks if md5sum is correct

        Returns:
            bool - True / False if checksums match
        """
        md5sum = self._get_md5sum(filename)

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

    def _image_installed(self, image_name, volume):
        """Checks if image is installed on a specified volume

        Returns:
            bool - True / False if image installed on a specified volume
        """
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
            if self._image_installed(image_name=image_name, volume=volume):
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
            self.api_handler.tm.sys.software.volumes.exec_cmd('reboot')

    def _wait_for_device_reboot(self, volume_name, timeout=600):
        """Waits for the device to be booted into a specified volume

        Returns:
            bool - True / False if reboot has been successful
        """
        end_time = time.time() + timeout

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

    def _upload_image(self, image):
        """Uploads an iso image to the device

        Returns:
            None
        """
        filename = os.path.basename(image)
        _URI = 'https://{hostname}/mgmt/cm/autodeploy/software-image-uploads/{filename}'.format(
            hostname=self.hostname, filename=filename)
        chunk_size = 512 * 1024
        size = os.path.getsize(image)
        headers = {'Content-Type': 'application/octet-stream'}
        requests.packages.urllib3.disable_warnings()
        start = 0

        with open(image, 'rb') as fileobj:
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
