"""Module for using a Cisco IOSXE WLC device over SSH."""
import time

from .ios_device import IOSDevice
from pyntc.errors import (
    RebootTimeoutError,
    OSInstallError,
    WaitingRebootTimeoutError,
)

INSTALL_MODE_FILE_NAME = "packages.conf"


class IOSXEWLCDevice(IOSDevice):
    """Cisco IOSXE WLC Device Implementation."""

    def _wait_for_device_start_reboot(self, timeout=600):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                self.show("show version")
            except Exception:  # noqa E722 # nosec
                return

        raise WaitingRebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def _wait_for_device_reboot(self, timeout=5400):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.open()
                self.show("show version")
                return
            except Exception:  # noqa E722 # nosec
                pass

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def install_os(self, image_name, install_mode_delay_factor=20, **vendor_specifics):
        """Installs the prescribed Network OS, which must be present before issuing this command.

        Args:
            image_name (str): Name of the IOS image to boot into

        Raises:
            OSInstallError: Unable to install OS Error type

        Returns:
            bool: False if no install is needed, true if the install completes successfully
        """
        timeout = vendor_specifics.get("timeout", 5400)
        if not self._image_booted(image_name):
            # Change boot statement to be boot system <flash>:packages.conf
            self.set_boot_options(INSTALL_MODE_FILE_NAME, **vendor_specifics)

            # Get the current fast_cli to set it back later to whatever it is
            current_fast_cli = self.fast_cli

            # Set fast_cli to False to handle install mode, 10+ minute installation
            self.fast_cli = False

            # Run install command (which reboots the device)
            command = f"install add file {self._get_file_system()}{image_name} activate commit prompt-level none"

            # Set a higher delay factor and send it in
            try:
                self.show(command, delay_factor=install_mode_delay_factor)
            except IOError:
                # Expected error IOError is raised from previous show command.
                pass

            # Wait for device to start reboot
            self._wait_for_device_start_reboot()

            # Wait for the reboot to finish
            self._wait_for_device_reboot(timeout=timeout)

            # Set FastCLI back to originally set when using install mode
            self.fast_cli = current_fast_cli

            # Verify the OS level
            if not self._image_booted(image_name):
                raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

            return True

        return False

    def show(self, command, expect_string=None, **netmiko_args):
        """Run command on device.

        Args:
            command (str): Command to be ran.
            expect_string (str, optional): Expected string from command output. Defaults to None.

        Returns:
            str: Output of command.
        """
        self.enable()
        return self._send_command(command, expect_string=expect_string, **netmiko_args)
