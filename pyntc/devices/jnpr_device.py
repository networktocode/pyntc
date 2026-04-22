"""Module for using a Juniper junOS device."""

import hashlib
import os
import re
import time
import warnings
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from jnpr.junos import Device as JunosNativeDevice
from jnpr.junos.exception import ConfigLoadError
from jnpr.junos.op.ethport import EthPortTable  # pylint: disable=import-error,no-name-in-module
from jnpr.junos.utils.config import Config as JunosNativeConfig
from jnpr.junos.utils.fs import FS as JunosNativeFS
from jnpr.junos.utils.scp import SCP
from jnpr.junos.utils.sw import SW as JunosNativeSW

from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs
from pyntc.devices.tables.jnpr.loopback import LoopbackTable  # pylint: disable=no-name-in-module
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    FileTransferError,
    OSInstallError,
    RebootTimeoutError,
)
from pyntc.utils.models import FileCopyModel

# Multipliers for Junos ``df``-style size suffixes. Junos formats available
# space with binary (1024-based) units in its ``<available-blocks format="...">``
# XML attribute (e.g., "126M", "1.0G").
_JUNOS_SIZE_UNIT_MULTIPLIERS = {
    "": 1,
    "B": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "P": 1024**5,
}
_JUNOS_AVAIL_FORMAT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([BKMGTP]?)\s*$", re.IGNORECASE)
# Default mount point to probe when callers do not specify one. ``/var/tmp`` is
# the standard destination for ``fs.cp`` transfers on Junos (remote device
# mount point, not a local temp directory).
_JUNOS_DEFAULT_FILE_SYSTEM = "/var/tmp"  # noqa: S108

# Hashing algorithms that Junos implements for the ``file checksum`` RPC.
# Junos does NOT implement sha512; callers passing it will be rejected at the
# driver boundary rather than surfacing PyEZ's raw ValueError deeper in the
# stack. Mirrors the pattern used by EOS and NXOS drivers.
JUNOS_SUPPORTED_HASHING_ALGORITHMS = {"md5", "sha1", "sha256"}


def _mount_encloses_path(mount, path):
    """Return True if ``mount`` is the filesystem that contains ``path``.

    Matches with directory-boundary semantics (the same rule ``df`` uses) so
    ``/vari`` is not mistaken for a prefix of ``/var/tmp``. ``/`` encloses
    every path.
    """
    if mount == "/":
        return True
    if path == mount:
        return True
    return path.startswith(mount.rstrip("/") + "/")


@fix_docs
class JunosDevice(BaseDevice):
    """Juniper JunOS Device Implementation."""

    vendor = "juniper"
    DEFAULT_TIMEOUT = 120

    def __init__(self, host, username, password, *args, **kwargs):  # noqa: D403
        """PyNTC device implementation for Juniper JunOS.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            args (tuple): Additional positional arguments to pass to the device.
            kwargs (dict): Additional keyword arguments to pass to the device.
        """
        super().__init__(host, username, password, *args, device_type="juniper_junos_netconf", **kwargs)

        self.native = JunosNativeDevice(*args, host=host, user=username, passwd=password, **kwargs)
        self.open()
        self.native.timeout = self.DEFAULT_TIMEOUT
        log.init(host=host)
        self.cu = JunosNativeConfig(self.native)  # pylint: disable=invalid-name
        self.fs = JunosNativeFS(self.native)  # pylint: disable=invalid-name
        self.sw = JunosNativeSW(self.native)  # pylint: disable=invalid-name

    def _file_copy_local_file_exists(self, filepath):
        return os.path.isfile(filepath)

    def _file_copy_local_md5(self, filepath, blocksize=2**20):
        if self._file_copy_local_file_exists(filepath):
            md5_hash = hashlib.md5()  # noqa: S324
            with open(filepath, "rb") as file_name:
                buf = file_name.read(blocksize)
                while buf:
                    md5_hash.update(buf)
                    buf = file_name.read(blocksize)
            return md5_hash.hexdigest()

    def _get_free_space(self, file_system=None):
        """Return free bytes on the filesystem containing ``file_system``.

        Probes the device via ``get-system-storage-information`` (invoked by
        PyEZ ``FS.storage_usage``) and parses the human-readable
        ``available-blocks`` ``format`` attribute (e.g., ``"126M"``, ``"1.0G"``)
        into bytes. The human-readable string is used rather than the raw
        block count because PyEZ does not expose a native block size and
        Junos block semantics can vary by release.

        ``file_system`` is resolved by **longest-prefix mount match** — the
        same logic ``df`` uses — so a caller asking about ``/var/tmp`` on a
        platform that only mounts ``/var`` (e.g., SRX hardware) still gets
        back the correct filesystem's free space. ``/`` is always a fallback
        when nothing more specific matches.

        Args:
            file_system (str, optional): Target path. When ``None`` (the
                default), the probe uses ``_JUNOS_DEFAULT_FILE_SYSTEM``
                (``/var/tmp`` — the standard destination for ``fs.cp`` copies
                on Junos).

        Returns:
            int: Free bytes available on the resolved filesystem.

        Raises:
            FileSystemNotFoundError: When no mount point encloses ``file_system``
                (i.e., not even ``/`` is present in ``storage_usage``).
            CommandError: When the ``avail`` format string cannot be parsed.
        """
        if file_system is None:
            file_system = _JUNOS_DEFAULT_FILE_SYSTEM

        usage = self.fs.storage_usage()
        best_info = None
        best_mount = None
        best_len = -1
        for _dev, info in usage.items():
            mount = info.get("mount")
            if not mount or not _mount_encloses_path(mount, file_system):
                continue
            if len(mount) > best_len:
                best_info = info
                best_mount = mount
                best_len = len(mount)

        if best_info is None:
            log.error(
                "Host %s: no mount encloses %s in storage_usage output.",
                self.host,
                file_system,
            )
            raise FileSystemNotFoundError(hostname=self.host, command="show system storage")

        avail = best_info.get("avail", "")
        match = _JUNOS_AVAIL_FORMAT_RE.match(str(avail))
        if match is None:
            log.error(
                "Host %s: could not parse avail %r for mount %s.",
                self.host,
                avail,
                best_mount,
            )
            raise CommandError(
                command="show system storage",
                message=f"Unable to parse available space {avail!r} for {best_mount}.",
            )
        size = float(match.group(1))
        multiplier = _JUNOS_SIZE_UNIT_MULTIPLIERS[match.group(2).upper()]
        free_bytes = int(size * multiplier)
        log.debug(
            "Host %s: %s bytes free on %s (resolved from %s).",
            self.host,
            free_bytes,
            best_mount,
            file_system,
        )
        return free_bytes

    def _get_interfaces(self):
        eth_ifaces = EthPortTable(self.native)
        eth_ifaces.get()

        loop_ifaces = LoopbackTable(self.native)
        loop_ifaces.get()

        ifaces = eth_ifaces.keys()
        ifaces.extend(loop_ifaces.keys())

        return ifaces

    def _image_booted(self, image_name, **vendor_specifics):
        raise NotImplementedError

    def _uptime_components(self, uptime_full_string):
        match_days = re.search(r"(\d+) days?", uptime_full_string)
        match_hours = re.search(r"(\d+) hours?", uptime_full_string)
        match_minutes = re.search(r"(\d+) minutes?", uptime_full_string)
        match_seconds = re.search(r"(\d+) seconds?", uptime_full_string)

        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0
        seconds = int(match_seconds.group(1)) if match_seconds else 0

        return days, hours, minutes, seconds

    def _uptime_to_seconds(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)

        seconds += days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60

        return seconds

    def _uptime_to_string(self, uptime_full_string):
        days, hours, minutes, seconds = self._uptime_components(uptime_full_string)
        return f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _wait_for_device_reboot(self, timeout=3600):
        start = time.time()
        disconnected = False
        while time.time() - start < timeout:
            if disconnected:
                try:
                    self.open()
                    return
                except:  # noqa E722 # nosec  # pylint: disable=bare-except
                    pass
            elif not self.connected:
                disconnected = True
            time.sleep(10)

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def backup_running_config(self, filename):
        """Backup current running configuration.

        Args:
            filename (str): Name used for backup file.
        """
        with open(filename, "w", encoding="utf-8") as file_name:
            file_name.write(self.running_config)

    @property
    def boot_options(self):
        """Get os version on device.

        Returns:
            (str): OS version on device.
        """
        return self.os_version

    def checkpoint(self, filename):
        """Create checkpoint file.

        Args:
            filename (str): Name of checkpoint file.
        """
        self.save(filename)

    def close(self):
        """Close connection to device."""
        if self.connected:
            self.native.close()

    def config(self, commands, format_type="set"):
        """Send configuration commands to a device.

        Args:
            commands (str, list): String with single command, or list with multiple commands.
            format_type (str, optional): Format type for the command. Defaults to "set".

        Raises:
            ConfigLoadError: Issue with loading the command.
            CommandError: Issue with the command provided, if its a single command, passed in as a string.
            CommandListError: Issue with a command in the list provided.
        """
        if isinstance(commands, str):
            try:
                self.cu.load(commands, format_type=format_type)
                self.cu.commit()
            except ConfigLoadError as err:
                raise CommandError(commands, err.message)
        else:
            try:
                for command in commands:
                    self.cu.load(command, format_type=format_type)

                self.cu.commit()
            except ConfigLoadError as err:
                raise CommandListError(commands, command, err.message)

    @property
    def connected(self):
        """Get connection status of device.

        Returns:
            (bool): True if connection is active. Otherwise, false.
        """
        return self.native.connected

    @property
    def uptime(self):
        """Get device uptime in seconds.

        Returns:
            (int): Device uptime in seconds.
        """
        try:
            native_uptime_string = self.native.facts["RE0"]["up_time"]
        except (AttributeError, TypeError):
            native_uptime_string = None

        if self._uptime is None:
            if native_uptime_string is not None:
                self._uptime = self._uptime_to_seconds(native_uptime_string)

        return self._uptime

    @property
    def uptime_string(self):
        """
        Get device uptime in format dd:hh:mm:ss.

        Returns:
            (str): Device uptime.
        """
        try:
            native_uptime_string = self.native.facts["RE0"]["up_time"]
        except (AttributeError, TypeError):
            native_uptime_string = None

        if self._uptime_string is None:
            self._uptime_string = self._uptime_to_string(native_uptime_string)

        return self._uptime_string

    @property
    def hostname(self):
        """Get device hostname.

        Returns:
            (str): Device hostname.
        """
        if self._hostname is None:
            self._hostname = self.native.facts.get("hostname")

        return self._hostname

    @property
    def interfaces(self):
        """Get list of interfaces.

        Returns:
            (list): List of interfaces.
        """
        if self._interfaces is None:
            self._interfaces = self._get_interfaces()

        return self._interfaces

    @property
    def fqdn(self):
        """Get fully qualified domain name.

        Returns:
            (str): Fully qualified domain name.
        """
        if self._fqdn is None:
            self._fqdn = self.native.facts.get("fqdn")

        return self._fqdn

    @property
    def model(self):
        """Get device model.

        Returns:
            (str): Device model.
        """
        if self._model is None:
            self._model = self.native.facts.get("model")

        return self._model

    @property
    def os_version(self):
        """Get OS version.

        Returns:
            (str): OS version.
        """
        if self._os_version is None:
            self._os_version = self.native.facts.get("version")

        return self._os_version

    @property
    def serial_number(self):
        """Get serial number.

        Returns:
            (str): Serial number.
        """
        if self._serial_number is None:
            self._serial_number = self.native.facts.get("serialnumber")

        return self._serial_number

    def file_copy(self, src, dest=None, **kwargs):
        """Copy file to device via SCP.

        Args:
            src (str): Name of file to be transferred.
            dest (str, optional): Path on device to save file. Defaults to None.
            kwargs (dict): Additional keyword arguments to pass to the `file_copy` command.

        Raises:
            FileTransferError: Raised when unable to verify file was transferred succesfully.
            NotEnoughFreeSpaceError: When the target filesystem has fewer free bytes
                than ``src`` requires.
        """
        if not self.file_copy_remote_exists(src, dest, **kwargs):
            if dest is None:
                dest = os.path.basename(src)

            self._check_free_space(os.path.getsize(src))

            with SCP(self.native) as scp:
                scp.put(src, remote_path=dest)

            if not self.file_copy_remote_exists(src, dest, **kwargs):
                raise FileTransferError(
                    message="Attempted file copy, but could not validate file existed after transfer"
                )

    # TODO: Make this an internal method since exposing file_copy should be sufficient
    def file_copy_remote_exists(self, src, dest=None, **kwargs):
        """Verify device already has existing file.

        Args:
            src (str): Source of local file.
            dest (str, optional): Path of file on device. Defaults to None.
            kwargs (dict): Additional keyword arguments to pass to the `file_copy` command.

        Returns:
            (bool): True if hashes of the file match. Otherwise, false.
        """
        if dest is None:
            dest = os.path.basename(src)

        local_hash = self._file_copy_local_md5(src)
        remote_hash = self.get_remote_checksum(dest)
        if local_hash is not None and local_hash == remote_hash:
            return True
        return False

    def install_os(self, image_name, checksum, hashing_algorithm="md5"):
        """Install OS on device and reboot.

        Args:
            image_name (str): Name of image.
            checksum (str): The checksum of the file.
            hashing_algorithm (str): The hashing algorithm to use. Valid values are 'md5', 'sha1', and 'sha256'. Defaults to 'md5'.

        """
        install_ok = self.sw.install(
            package=image_name,
            checksum=checksum,
            checksum_algorithm=hashing_algorithm,
            progress=True,
            validate=True,
            no_copy=True,
            timeout=3600,
        )

        # Sometimes install() returns a tuple of (ok, msg). Other times it returns a single bool
        if isinstance(install_ok, tuple):
            install_ok = install_ok[0]

        if not install_ok:
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

        self.reboot(wait_for_reload=True)

    def open(self):
        """Open connection to device."""
        if not self.connected:
            self.native.open()

    def reboot(self, wait_for_reload=False, timeout=3600, confirm=None):
        """
        Reload the controller or controller pair.

        Args:
            wait_for_reload (bool): Whether the reboot method should wait for the device to come back up before returning. Defaults to False.
            timeout (int, optional): Time in seconds to wait for the device to return after reboot. Defaults to 1 hour.
            confirm (None): Not used. Deprecated since v0.17.0.

        Example:
            >>> device = JunosDevice(**connection_args)
            >>> device.reboot()
            >>>
        """
        if confirm is not None:
            warnings.warn("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        self.sw.reboot(in_min=0)
        if wait_for_reload:
            self._wait_for_device_reboot(timeout=timeout)

    def rollback(self, filename):
        """Rollback to a specific configuration file.

        Args:
            filename (str): Filename to rollback device to.
        """
        temp_file = NamedTemporaryFile()  # pylint: disable=consider-using-with

        with SCP(self.native) as scp:
            scp.get(filename, local_path=temp_file.name)

        self.cu.load(path=temp_file.name, format="text", overwrite=True)
        self.cu.commit()

        temp_file.close()

    @property
    def running_config(self):
        """Get running configuration.

        Returns:
            (str): Running configuration.
        """
        return self.show("show config")

    def save(self, filename=None):
        """
        Save current configuration to device.

        If filename is provided, save current configuration to file.

        Args:
            filename (str, optional): Filename to save current configuration. Defaults to None.

        Returns:
            (bool): True if new file created for save file. Otherwise, just returns if save is to default name.
        """
        if filename is None:
            self.cu.commit(dev_timeout=300)
            return

        temp_file = NamedTemporaryFile(mode="w")  # pylint: disable=consider-using-with
        temp_file.write(self.startup_config)
        temp_file.flush()

        with SCP(self.native) as scp:
            scp.put(temp_file.name, remote_path=filename)

        temp_file.close()
        return True

    def set_boot_options(self, sys):
        """Set boot options.

        Args:
            sys (str): Name of image to set boot option to.

        Raises:
            NotImplementedError: Method currently not implemented.
        """
        raise NotImplementedError

    def show(self, commands):
        """Send configuration commands to a device.

        Args:
            commands (str, list): String with single command, or list with multiple commands.

        Raises:
            CommandError: Issue with the command provided.
            CommandListError: Issue with a command in the list provided.
        """
        original_commands_is_str = isinstance(commands, str)
        if original_commands_is_str:
            commands = [commands]
        responses = []
        for command in commands:
            if not command.startswith("show"):
                if original_commands_is_str:
                    raise CommandError(command, 'Juniper "show" commands must begin with "show".')
                raise CommandListError(commands, command, 'Juniper "show" commands must begin with "show".')

            response = self.native.cli(command, warning=False)
            responses.append(response)
        if original_commands_is_str:
            return responses[0]
        return responses

    @property
    def startup_config(self):
        """Get startup configuration.

        Returns:
            (str): Startup configuration.
        """
        return self.show("show config")

    def check_file_exists(self, filename):
        """Check if a remote file exists by filename.

        Args:
            filename (str): The name of the file to check for on the remote device.

        Returns:
            (bool): True if the remote file exists, False if it doesn't.
        """
        return self.fs.ls(filename) is not None

    def get_remote_checksum(self, filename, hashing_algorithm="md5"):
        """Get the checksum of a remote file.

        Args:
            filename (str): The name of the file to check for on the remote device.
            hashing_algorithm (str): The hashing algorithm to use. Valid values are
                those in ``JUNOS_SUPPORTED_HASHING_ALGORITHMS`` (``md5``, ``sha1``,
                ``sha256``). Defaults to ``md5``.

        Returns:
            (str): The checksum of the remote file or None if the file is not found.

        Raises:
            ValueError: When ``hashing_algorithm`` is not one Junos implements.
        """
        if hashing_algorithm.lower() not in JUNOS_SUPPORTED_HASHING_ALGORITHMS:
            raise ValueError(
                f"Unsupported hashing algorithm '{hashing_algorithm}' for Junos. "
                f"Supported algorithms: {sorted(JUNOS_SUPPORTED_HASHING_ALGORITHMS)}"
            )
        return self.fs.checksum(path=filename, calc=hashing_algorithm)

    def compare_file_checksum(self, checksum, filename, hashing_algorithm="md5"):
        """Compare the checksum of a local file with a remote file.

        Args:
            checksum (str): The checksum of the file.
            filename (str): The name of the file to check for on the remote device.
            hashing_algorithm (str): The hashing algorithm to use. Valid values are 'md5', 'sha1', and 'sha256'. Defaults to 'md5'.

        Returns:
            (bool): True if the checksums match, False otherwise.
        """
        return checksum == self.get_remote_checksum(filename, hashing_algorithm)

    def remote_file_copy(self, src: FileCopyModel = None, dest=None, file_system: str | None = None, **kwargs):
        """Copy a file to a remote device.

        Args:
            src (FileCopyModel): The source file model.
            dest (str): The destination file path on the remote device.
            file_system (str, optional): Mount point used for the pre-transfer
                free-space check. When ``None`` (the default), the probe uses
                ``_JUNOS_DEFAULT_FILE_SYSTEM`` (``/var/tmp``).
            **kwargs (Any): Accepted for parity with ``BaseDevice.remote_file_copy``;
                other drivers may forward extra options.

        Raises:
            TypeError: If src is not an instance of FileCopyModel.
            FileTransferError: If there is an error during file transfer or if the file cannot be verified after transfer.
            NotEnoughFreeSpaceError: If ``src.file_size_bytes`` is set and the
                target mount point has fewer free bytes than ``src.file_size_bytes``.
                When ``file_size`` is omitted from ``src`` the pre-transfer space
                check is skipped entirely.
        """
        if not isinstance(src, FileCopyModel):
            raise TypeError("src must be an instance of FileCopyModel")

        if self.verify_file(src.checksum, dest, hashing_algorithm=src.hashing_algorithm):
            return

        self._pre_transfer_space_check(src, file_system=file_system)

        # Junos ``fs.cp`` requires the filename in the URL; append ``src.file_name``
        # when the URL carries no path so callers can point at a bare host.
        source_url = src.download_url
        if not urlparse(source_url).path.strip("/"):
            source_url = f"{source_url.rstrip('/')}/{src.file_name}"

        if not self.fs.cp(from_path=source_url, to_path=dest, dev_timeout=src.timeout):
            raise FileTransferError(message=f"Unable to copy file from remote url {src.clean_url}")

        # Some devices take a while to sync the filesystem after a copy but netconf returns before the sync completes
        for _ in range(5):
            if self.verify_file(src.checksum, dest, hashing_algorithm=src.hashing_algorithm):
                return
            time.sleep(30)

        log.error(
            "Host %s: Attempted remote file copy, but could not validate file existed after transfer",
            self.host,
        )
        raise FileTransferError

    def verify_file(self, checksum, filename, hashing_algorithm="md5"):
        """Verify a file on the remote device by confirming the file exists and validate the checksum.

        Args:
            checksum (str): The checksum of the file.
            filename (str): The name of the file to check for on the remote device.
            hashing_algorithm (str): The hashing algorithm to use (default: "md5").

        Returns:
            (bool): True if the file is verified successfully, False otherwise.
        """
        return self.check_file_exists(filename) and self.compare_file_checksum(checksum, filename, hashing_algorithm)
