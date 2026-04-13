"""Module for using an NXOS device over NX-API."""

import os
import re
import time
from urllib.parse import urlparse

from netmiko import ConnectHandler
from pynxos.device import Device as NXOSNative
from pynxos.errors import CLIError
from pynxos.features.file_copy import FileTransferError as NXOSFileTransferError
from requests.exceptions import ConnectTimeout, ReadTimeout

from pyntc import log
from pyntc.devices.base_device import BaseDevice, RollbackError, fix_docs
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    FileTransferError,
    NTCFileNotFoundError,
    OSInstallError,
    RebootTimeoutError,
)
from pyntc.utils.models import FileCopyModel


@fix_docs
class NXOSDevice(BaseDevice):
    """Cisco NXOS Device Implementation."""

    vendor = "cisco"

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(self, host, username, password, transport="http", timeout=30, port=None, verify=True, **kwargs):  # noqa: D403
        """PyNTC Device implementation for Cisco IOS.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            transport (str, optional): Transport protocol to connect to device. Defaults to "http".
            timeout (int, optional): Timeout in seconds. Defaults to 30.
            port (int, optional): Port used to connect to device. Defaults to None.
            verify (bool, optional): SSL verification.
            kwargs (dict): Left for compatibility with other tools, for instance nautobot-inventory may pass additional kwargs.

        """
        super().__init__(host, username, password, device_type="cisco_nxos_nxapi")
        self.transport = transport
        self.timeout = timeout
        # Use self.native for NXAPI
        self.native = NXOSNative(
            host, username, password, transport=transport, timeout=timeout, port=port, verify=verify
        )
        # Use self.native_ssh for Netmiko ssh
        self.native_ssh = None
        self._connected = False
        self.open()
        log.init(host=host)

    def _image_booted(self, image_name, **vendor_specifics):
        version_data = self.show("show version", raw_text=True)
        return bool(re.search(image_name, version_data))

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        while time.time() - start < timeout:
            try:  # NXOS stays online, when it installs OS
                self.refresh()
                if self.uptime < 180:
                    log.info("Host %s: Device rebooted.", self.host)
                    return
            except:  # noqa E722 # nosec  # pylint: disable=bare-except
                log.debug("Host %s: Pausing for 10 sec before retrying.", self.host)
                time.sleep(10)

        log.error("Host %s: Device timed out while rebooting.", self.host)
        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def refresh(self):
        """Refresh caches on device instance."""
        if hasattr(self.native, "_facts"):
            delattr(self.native, "_facts")
        super().refresh()

    def backup_running_config(self, filename):
        """Backup running configuration.

        Args:
            filename (str): Name of backup file.
        """
        self.native.backup_running_config(filename)
        log.debug("Host %s: Running config backed up.", self.host)

    @property
    def boot_options(self):
        """Get current boot variables.

        Returns:
            (dict): e.g . {"kick": "router_kick.img", "sys": "router_sys.img"}
        """
        boot_options = self.native.get_boot_options()
        log.debug("Host %s: the boot options are %s", self.host, boot_options)
        return boot_options

    def checkpoint(self, filename):
        """Save a checkpoint of the running configuration to the device.

        Args:
            filename (str): The filename to save the checkpoint on the remote device.
        """
        log.debug("Host %s: checkpoint is %s.", self.host, filename)
        return self.native.checkpoint(filename)

    def close(self):
        """Disconnect from device."""
        if self.connected:
            self.native_ssh.disconnect()
            self._connected = False
            log.debug("Host %s: Connection closed.", self.host)

    def config(self, command):
        """Send configuration command.

        Args:
            command (str, list): command to be sent to the device.

        Raises:
            CommandError: Error if command is not succesfully ran on device.
        """
        if isinstance(command, list):
            try:
                self.native.config_list(command)
                log.info("Host %s: Configured with commands: %s", self.host, command)
            except CLIError as e:
                log.error("Host %s: Command error with commands: %s and error message %s", self.host, command, str(e))
                raise CommandListError(command, e.command, str(e))
        else:
            try:
                self.native.config(command)
                log.info("Host %s: Device configured with command %s.", self.host, command)
            except CLIError as e:
                log.error("Host %s: Command error with commands: %s and error message %s", self.host, command, str(e))
                raise CommandError(command, str(e))

    @property
    def uptime(self):
        """Get uptime of the device in seconds.

        Returns:
            (int): Uptime of the device in seconds.
        """
        if self._uptime is None:
            self._uptime = self.native.facts.get("uptime")

        log.debug("Host %s: Uptime %s", self.host, self._uptime)
        return self._uptime

    @property
    def uptime_string(self):
        """Get uptime in format dd:hh:mm.

        Returns:
            (str): Uptime of device.
        """
        if self._uptime_string is None:
            self._uptime_string = self.native.facts.get("uptime_string")

        return self._uptime_string

    @property
    def hostname(self):
        """Get hostname of the device.

        Returns:
            (str): Hostname of the device.
        """
        if self._hostname is None:
            self._hostname = self.native.facts.get("hostname")

        log.debug("Host %s: Hostname %s", self.host, self._hostname)
        return self._hostname

    @property
    def interfaces(self):
        """Get list of interfaces.

        Returns:
            (list): List of interfaces.
        """
        if self._interfaces is None:
            self._interfaces = self.native.facts.get("interfaces")

        log.debug("Host %s: Interfaces %s", self.host, self._interfaces)
        return self._interfaces

    @property
    def vlans(self):
        """Get list of vlans.

        Returns:
            (list): List of vlans on the device.
        """
        if self._vlans is None:
            self._vlans = self.native.facts.get("vlans")

        log.debug("Host %s: Vlans %s", self.host, self._vlans)
        return self._vlans

    @property
    def fqdn(self):
        """Get fully qualified domain name.

        Returns:
            (str): Fully qualified domain name.
        """
        if self._fqdn is None:
            self._fqdn = self.native.facts.get("fqdn")

        log.debug("Host %s: FQDN %s", self.host, self._fqdn)
        return self._fqdn

    @property
    def model(self):
        """Get device model.

        Returns:
            (str): Model of device.
        """
        if self._model is None:
            self._model = self.native.facts.get("model")

        log.debug("Host %s: Model %s", self.host, self._model)
        return self._model

    @property
    def os_version(self):
        """Get device version.

        Returns:
            (str): Device version.
        """
        if self._os_version is None:
            self._os_version = self.native.facts.get("os_version")

        log.debug("Host %s: OS version %s", self.host, self._os_version)
        return self._os_version

    @property
    def serial_number(self):
        """Get device serial number.

        Returns:
            (str): Device serial number.
        """
        if self._serial_number is None:
            self._serial_number = self.native.facts.get("serial_number")

        log.debug("Host %s: Serial number %s", self.host, self._serial_number)
        return self._serial_number

    def file_copy(self, src, dest=None, file_system="bootflash:"):
        """Send a local file to the device.

        Args:
            src (str): Path to the local file to send.
            dest (str, optional): The destination file path. Defaults to basename of source path.
            file_system (str, optional): [The file system for the remote file. Defaults to "bootflash:".

        Raises:
            FileTransferError: Error if transfer of file cannot be verified.
        """
        if not self.file_copy_remote_exists(src, dest, file_system):
            dest = dest or os.path.basename(src)
            try:
                file_copy = self.native.file_copy(  # pylint: disable=assignment-from-no-return
                    src, dest, file_system=file_system
                )  # pylint: disable=assignment-from-no-return
                log.info("Host %s: File %s transferred successfully.", self.host, src)
                if not self.file_copy_remote_exists(src, dest, file_system):
                    log.error(
                        "Host %s: Attempted file copy, but could not validate file existed after transfer %s",
                        self.host,
                        FileTransferError.default_message,
                    )
                    raise FileTransferError
                return file_copy

            except NXOSFileTransferError as err:
                log.error("Host %s: NXOS file transfer error %s", self.host, str(err))
                raise FileTransferError

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, file_system="bootflash:"):
        """Check if a remote file exists.

        Args:
            src (str): Path to the local file to send.
            dest (str, optional): The destination file path to be saved on remote device. Defaults to basename of source path.
            file_system (str, optional): The file system for the remote file. Defaults to "bootflash:".

        Returns:
            (bool): True if the remote file exists. Otherwise, false.
        """
        dest = dest or os.path.basename(src)
        log.debug(
            "Host %s: File %s exists on remote %s.",
            self.host,
            src,
            self.native.file_copy_remote_exists(src, dest, file_system=file_system),
        )
        return self.native.file_copy_remote_exists(src, dest, file_system=file_system)

    ###
    # MM Begin
    ###
    def _get_file_system(self):
        """Determine the default file system or directory for device.

        Returns:
            (str): The name of the default file system or directory for the device.

        Raises:
            FileSystemNotFoundError: When the module is unable to determine the default file system.
        """
        raw_data = self.show("dir")
        try:
            file_system = re.match(r"\s*.*?(\S+:)", raw_data).group(1)
        except AttributeError:
            log.error("Host %s: File system not found with command 'dir'.", self.host)
            raise FileSystemNotFoundError(hostname=self.host, command="dir")

        log.debug("Host %s: File system %s.", self.host, file_system)
        return file_system

    def check_file_exists(self, filename, file_system=None):
        """Check if a remote file exists by filename.

        Args:
            filename (str): The name of the file to check for on the remote device.
            file_system (str): Supported only for Arista. The file system for the
                remote file. If no file_system is provided, then the `get_file_system`
                method is used to determine the correct file system to use.

        Returns:
            (bool): True if the remote file exists, False if it doesn't.

        Raises:
            CommandError: If there is an error in executing the command to check if the file exists.
        """
        exists = False

        file_system = file_system or self._get_file_system()
        command = f"dir {file_system}/{filename}"
        result = self.native_ssh.send_command(command, read_timeout=30)

        log.debug(
            "Host %s: Checking if file %s exists on remote with command '%s' and result: %s",
            self.host,
            filename,
            command,
            result,
        )

        # Check for error patterns
        if re.search(r"% Error listing directory|No such file|No files found|Path does not exist", result):
            log.debug("Host %s: File %s does not exist on remote.", self.host, filename)
            exists = False
        elif filename in result:
            # NXOS shows file details directly, just check if filename appears in output
            log.debug("Host %s: File %s exists on remote.", self.host, filename)
            exists = True
        else:
            raise CommandError(command, f"Unable to determine if file {filename} exists on remote: {result}")

        return exists

    def get_remote_checksum(self, filename, hashing_algorithm="md5", **kwargs):
        """Get the checksum of a file."""
        # Validate hashing algorithm
        if hashing_algorithm not in {"md5", "sha512"}:
            log.error(
                "Host %s: Unsupported hashing algorithm %s. Supported algorithms are: md5, sha512",
                self.host,
                hashing_algorithm,
            )
            raise ValueError(f"hashing_algorithm must be either 'md5' or 'sha512', got '{hashing_algorithm}'")

        # Determine file system
        file_system = kwargs.get("file_system")
        if file_system is None:
            file_system = self._get_file_system()

        # Normalize file_system
        if not file_system.startswith("/") and not file_system.endswith(":"):
            file_system = f"{file_system}:"

        # Use NXOS verify command to get the checksum
        # Example: show file bootflash:nautobot.png sha512sum
        command = f"show file {file_system}/{filename} {hashing_algorithm}sum"

        try:
            result = self.native_ssh.send_command(command, read_timeout=30)
            log.debug(
                "Host %s: Getting remote checksum for file %s with command '%s' and result: %s",
                self.host,
                filename,
                command,
                result,
            )

            # Match the checksum from output
            # Example: show file bootflash:nautobot.png sha512sum
            match = re.search(r"([a-fA-F0-9]{32,})", result)
            if match:
                remote_checksum = match.group(1).lower()
                log.debug("Host %s: Remote checksum for %s: %s", self.host, filename, remote_checksum)
                return remote_checksum

            log.error("Host %s: Could not parse checksum from output: %s", self.host, result)
            raise CommandError(command, f"Could not parse checksum from output: {result}")

        except Exception as e:
            log.error("Host %s: Error getting remote checksum: %s", self.host, str(e))
            raise CommandError(command, f"Error getting remote checksum: {str(e)}")

    def remote_file_copy(self, src: FileCopyModel, dest=None, file_system=None, **kwargs):
        """Copy a file from remote source to device.  Skips if file already exists and is verified on remote device.

        Args:
            src (FileCopyModel): The source file model with transfer parameters.
            dest (str): Destination filename (defaults to src.file_name).
            file_system (str): Device filesystem (auto-detected if not provided).
            **kwargs (Any): Passible parameters such as file_system.

        Raises:
            TypeError: If src is not a FileCopyModel.
            FileTransferError: If transfer or verification fails.
            FileSystemNotFoundError: If filesystem cannot be determined.
        """
        # Validate input
        if not isinstance(src, FileCopyModel):
            raise TypeError("src must be an instance of FileCopyModel")
        timeout = src.timeout or 30

        # Determine file system
        if file_system is None:
            file_system = self._get_file_system()

        # Determine destination
        if dest is None:
            dest = src.file_name

        # Handle url parsing and validation
        supported_schemes = ["http", "https", "scp", "ftp", "sftp", "tftp"]
        if src.scheme not in supported_schemes:
            raise ValueError(f"Unsupported scheme: {src.scheme}")
        parsed = urlparse(src.clean_url)
        if parsed.query:
            log.warning(
                "Host %s: URL query parameters are not supported and will be ignored for file copy operations on Cisco devices. URL: %s",
                self.host,
                src.download_url,
            )
        url = src.clean_url
        if src.username or src.token:
            credentials = src.username or ""
            if src.token:
                credentials = f"{credentials}:{src.token}" if credentials else src.token
            url = src.clean_url.replace(f"{src.scheme}://", f"{src.scheme}://{credentials}@", 1)

        log.debug(
            "Host %s: Verifying file %s exists before attempting a copy",
            self.host,
            dest,
        )
        if not self.verify_file(src.checksum, dest, hashing_algorithm=src.hashing_algorithm, file_system=file_system):
            current_prompt = self.native_ssh.find_prompt()

            # Define prompt mapping for expected prompts during file copy
            prompt_answers = {
                r"Password": src.token or "",
                r"Source username": src.username or "",
                r"yes/no|Are you sure you want to continue connecting": "yes",
                r"(confirm|Address or name of remote host|Source filename|Destination filename)": "",
            }
            keys = list(prompt_answers.keys()) + [re.escape(current_prompt)]
            expect_regex = f"({'|'.join(keys)})"

            # Construct copy command
            command = f"copy {url} {file_system}"
            if src.vrf:
                command += f" vrf {src.vrf}"

            log.debug("Host %s: Starting remote file copy for %s to %s/%s", self.host, src.file_name, file_system, dest)
            output = self.native_ssh.send_command(command, expect_string=expect_regex, read_timeout=timeout)

            while current_prompt not in output:
                # Check for success message in output to break loop and avoid waiting for next prompt
                if re.search(r"Copy complete|bytes copied in|File transfer successful", output, re.IGNORECASE):
                    log.info(
                        "Host %s: File %s transferred successfully with output: %s", self.host, src.file_name, output
                    )
                    break
                # Check for errors explicitly to avoid infinite loops on failure
                if re.search(r"(Error|Invalid|Failed|Aborted|denied)", output, re.IGNORECASE):
                    log.error("Host %s: File transfer error %s", self.host, FileTransferError.default_message)
                    raise FileTransferError
                for prompt, answer in prompt_answers.items():
                    if re.search(prompt, output, re.IGNORECASE):
                        output = self.native_ssh.send_command_timing(answer, read_timeout=timeout)
                        break  # Exit the for loop and check the new output for the next prompt

            # Verify file after transfer
            if not self.verify_file(
                src.checksum, dest, hashing_algorithm=src.hashing_algorithm, file_system=file_system
            ):
                log.error(
                    "Host %s: File verification failed after transfer for file %s",
                    self.host,
                    dest,
                )
                raise FileTransferError("File verification failed after transfer")

            log.info(
                "Host %s: File %s transferred successfully.",
                self.host,
                dest,
            )
        else:
            log.info(
                "Host %s: File %s already exists on remote and passed verification. File copy not performed.",
                self.host,
                dest,
            )

    def verify_file(self, checksum, filename, hashing_algorithm="md5", **kwargs):
        """Verify a file on the device by comparing checksums.

        Args:
            checksum (str): The expected checksum of the file.
            filename (str): The name of the file on the device.
            hashing_algorithm (str): The hashing algorithm to use (default: "md5").
            **kwargs (Any):  Passible parameters such as file_system.

        Returns:
            (bool): True if the file is verified successfully, False otherwise.
        """
        exists = self.check_file_exists(filename, **kwargs)
        device_checksum = (
            self.get_remote_checksum(filename, hashing_algorithm=hashing_algorithm, **kwargs) if exists else None
        )
        if checksum == device_checksum:
            log.debug("Host %s: Checksum verification successful for file %s", self.host, filename)
            return True

        log.debug(
            "Host %s: Checksum verification failed for file %s - Expected: %s, Actual: %s",
            self.host,
            filename,
            checksum,
            device_checksum,
        )
        return False

    ###
    # MM End
    ###

    def install_os(self, image_name, **vendor_specifics):
        """Upgrade device with provided image.

        Args:
            image_name (str): Name of the image file to upgrade the device to.
            vendor_specifics (dict): Vendor specific options.

        Raises:
            OSInstallError: Error if boot option is not set to new image.

        Returns:
            (bool): True if new image is boot option on device. Otherwise, false.
        """
        self.native.show("terminal dont-ask")
        timeout = vendor_specifics.get("timeout", 3600)
        if not self._image_booted(image_name):
            log.info("Host %s: Setting Image %s in boot options.", self.host, image_name)
            self.set_boot_options(image_name, **vendor_specifics)
            log.info("Host %s: Waiting for device reload.", self.host)
            self._wait_for_device_reboot(timeout=timeout)
            if not self._image_booted(image_name):
                log.error("Host %s: OS install error for image %s", self.host, image_name)
                raise OSInstallError(hostname=self.hostname, desired_boot=image_name)
            log.info("Host %s: OS image %s installed successfully.", self.host, image_name)
            return True

        log.info("Host %s: Image %s is already running on the device.", self.host, image_name)
        return False

    @property
    def connected(self):  # noqa: D401
        """
        Get connection status of the device.

        Returns:
            (bool): True if the device is connected, else False.
        """
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value

    def is_active(self):
        """
        Determine if the current processor is the active processor.

        Returns:
            (bool): True if the processor is active or does not support HA, else False.
        """
        return self.redundancy_state in self.active_redundancy_states

    def open(self):
        """Open a connection to the network device."""
        if self.connected:
            try:
                self.native_ssh.find_prompt()
            except:  # noqa E722  # pylint: disable=bare-except
                self._connected = False

        if not self.connected:
            self.native_ssh = ConnectHandler(
                device_type="cisco_nxos",
                host=self.host,
                username=self.username,
                password=self.password,
                port=22,
                timeout=self.timeout,
            )
            self._connected = True

        log.debug("Host %s: SSH connection opened successfully.", self.host)

    def reboot(self, wait_for_reload=False, **kwargs):
        """
        Reload the controller or controller pair.

        Args:
            wait_for_reload (bool): Whether or not reboot method should also run _wait_for_device_reboot(). Defaults to False.
            kwargs (dict): Additional arguments to pass to reboot method.

        Raises:
            RebootTimerError: When the device is still unreachable after the timeout period.

        Example:
            >>> device = NXOSDevice(**connection_args)
            >>> device.reboot()
            >>
        """
        if kwargs.get("confirm"):
            log.warning("Passing 'confirm' to reboot method is deprecated.")
            raise DeprecationWarning("Passing 'confirm' to reboot method is deprecated.")
        try:
            self.native.show_list(["terminal dont-ask", "reload"])
            # The native reboot is not always properly disabling confirmation. Above is more consistent.
            # self.native.reboot(confirm=True)
        except ReadTimeout as expected_exception:
            log.info("Host %s: Device rebooted.", self.host)
            log.info("Hit expected exception during reload: %s", expected_exception.__class__)
        if wait_for_reload:
            time.sleep(10)
            self._wait_for_device_reboot()
        log.info("Host %s: Device rebooted.", self.host)

    def rollback(self, filename):
        """Rollback configuration to specified file.

        Args:
            filename (str): Name of the file to rollback to.

        Raises:
            RollbackError: Error if rollback command is unsuccesfull.
        """
        try:
            self.native.rollback(filename)
            log.info("Host %s: Rollback to %s.", self.host, filename)
        except CLIError:
            log.error("Host %s: Rollback unsuccessful. %s may not exist.", self.host, filename)
            raise RollbackError(f"Rollback unsuccessful, {filename} may not exist.")

    @property
    def running_config(self):
        """Get running configuration of device.

        Returns:
            (str): Running configuration of device.
        """
        log.debug("Host %s: Show running config.", self.host)
        return self.native.running_config

    def save(self, filename="startup-config"):
        """Save a device's running configuration.

        Args:
            filename (str, optional): Filename to save running configuration to. Defaults to "startup-config".

        Returns:
            (bool): True if configuration is saved.
        """
        log.debug("Host %s: Copy running config with name %s.", self.host, filename)
        return self.native.save(filename=filename)

    def set_boot_options(self, image_name, kickstart=None, **vendor_specifics):
        """Set boot variables.

        Args:
            image_name (str): Main system image file.
            kickstart (str, optional): Kickstart filename. Defaults to None.
            vendor_specifics (dict): Vendor specific options.

        Raises:
            NTCFileNotFoundError: Error if either image_name or kickstart image not found on device.
        """
        file_system = vendor_specifics.get("file_system")
        if file_system is None:
            file_system = "bootflash:"

        file_system_files = self.show(f"dir {file_system}", raw_text=True)
        if re.search(image_name, file_system_files) is None:
            log.error("Host %s: File not found error for image %s.", self.host, image_name)
            raise NTCFileNotFoundError(hostname=self.hostname, file=image_name, directory=file_system)

        if kickstart is not None:
            if re.search(kickstart, file_system_files) is None:
                log.error("Host %s: File not found error for image %s.", self.host, image_name)
                raise NTCFileNotFoundError(hostname=self.hostname, file=kickstart, directory=file_system)

            kickstart = file_system + kickstart

        image_name = file_system + image_name
        try:
            self.native.set_boot_options(image_name, kickstart=kickstart)
        except (ReadTimeout, ConnectTimeout):
            pass
        log.info("Host %s: boot options have been set to %s", self.host, image_name)

    def set_timeout(self, timeout):
        """Set timeout value on device connection.

        Args:
            timeout (int): Timeout value.
        """
        log.debug("Host %s: Timeout set to %s.", self.host, timeout)
        self.native.timeout = timeout

    def show(self, command, raw_text=False):
        """Send a non-configuration command.

        Args:
            command (str): The command to send to the device.
            raw_text (bool, optional): Whether to return raw text or structured data. Defaults to False.

        Raises:
            CommandError: Error message stating which command failed.

        Returns:
            (str): Results of the command ran.
        """
        log.debug("Host %s: Successfully executed command 'show' with responses.", self.host)
        if isinstance(command, list):
            try:
                log.debug("Host %s: Successfully executed command 'show' with commands %s.", self.host, command)
                return self.native.show_list(command, raw_text=raw_text)
            except CLIError as e:
                log.error("Host %s: Command error for command %s with message %s.", self.host, e.command, str(e))
                raise CommandListError(command, e.command, str(e))
        try:
            log.debug("Host %s: Successfully executed command 'show'.", self.host)
            return self.native.show(command, raw_text=raw_text)
        except CLIError as e:
            log.error("Host %s: Command error %s.", self.host, str(e))
            raise CommandError(command, str(e))

    @property
    def startup_config(self):
        """Get startup configuration.

        Returns:
            (str): Startup configuration.
        """
        return self.show("show startup-config", raw_text=True)
