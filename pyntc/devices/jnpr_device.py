"""Module for using a Juniper junOS device."""

import hashlib
import os
import re
import time
import warnings
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from jnpr.junos import Device as JunosNativeDevice
from jnpr.junos.exception import (ConfigLoadError, ConnectClosedError,
                                  RpcError, RpcTimeoutError)
from jnpr.junos.op.ethport import \
    EthPortTable  # pylint: disable=import-error,no-name-in-module
from jnpr.junos.utils.config import Config as JunosNativeConfig
from jnpr.junos.utils.fs import FS as JunosNativeFS
from jnpr.junos.utils.scp import SCP
from jnpr.junos.utils.sw import SW as JunosNativeSW

from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs
from pyntc.devices.tables.jnpr.loopback import \
    LoopbackTable  # pylint: disable=no-name-in-module
from pyntc.errors import (CommandError, CommandListError,
                          FileSystemNotFoundError, FileTransferError,
                          OSInstallError, RebootTimeoutError)
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
    DEFAULT_TIMEOUT = 180

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
        self._is_virtual_chassis = None

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

    def _wait_for_device_reboot(self, original_uptime, timeout=7200):
        """Block until the device reboots and accepts a fresh connection.

        Drops the existing NETCONF session and polls for the device to come back.
        The reboot is considered complete when a new connection succeeds and the
        device reports an uptime lower than ``original_uptime`` (i.e., it has
        booted since the reboot was issued).

        The pre-reboot session must be discarded first: once the device restarts,
        PyEZ still reports it as connected even though the transport is dead, so it
        is closed here to force each probe to establish a fresh connection.

        Args:
            original_uptime (int): Device uptime in seconds captured before the reboot.
            timeout (int, optional): Max seconds to wait for the device to return. Defaults to 2 hours.
        """
        start = time.time()

        # Drop the pre-reboot NETCONF session so subsequent probes can't read from
        # a stale connection PyEZ still reports as connected.
        try:
            self.close()
        except Exception as close_exc:  # pylint: disable=broad-exception-caught
            log.debug("Host %s: Pre-reboot disconnect raised %s (ignored).", self.host, close_exc)

        while time.time() - start < timeout:
            try:
                self.open()
                self._uptime = None
                current_uptime = self.uptime
                if current_uptime is not None and current_uptime < original_uptime:
                    log.info(
                        "Host %s: Device rebooted (uptime %ss < pre-reboot %ss).",
                        self.host,
                        current_uptime,
                        original_uptime,
                    )
                    return
                log.debug(
                    "Host %s: Reachable but uptime %ss >= pre-reboot %ss; still waiting.",
                    self.host,
                    current_uptime,
                    original_uptime,
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.debug("Host %s: Reboot probe failed (%s); will retry.", self.host, exc)
                self.native.connected = False
            time.sleep(10)

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def _wait_for_system_snapshot(self, timeout=1800, interval=180):
        """Poll device to verify system snapshot completion.

        Periodically checks ``show system snapshot media internal`` to verify the snapshot
        was successfully taken. Used when the ``request system snapshot`` RPC times out.

        Args:
            timeout (int, optional): Max seconds to wait for snapshot verification. Defaults to 1800 (30 minutes).
            interval (int, optional): Seconds between verification polls. Defaults to 180 (3 minutes).

        Raises:
            OSInstallError: When the snapshot verification indicates a failure.
        """
        start = time.time()

        while time.time() - start < timeout:
            try:
                output = self.native.cli("show system snapshot media internal")
                if "snapshot" in output.lower():
                    log.info("Host %s: System snapshot verified.", self.host)
                    return
                log.debug("Host %s: Snapshot verification in progress; will retry.", self.host)

            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.debug("Host %s: Snapshot verification poll failed (%s); will retry.", self.host, exc)

            time.sleep(interval)

        log.error("Host %s: System snapshot did not complete within %s seconds.", self.host, timeout)
        raise OSInstallError(hostname=self.hostname, desired_boot="system snapshot")

    def backup_running_config(self, filename):
        """Backup current running configuration.

        Args:
            filename (str): Name used for backup file.
        """
        with open(filename, "w", encoding="utf-8") as file_name:
            file_name.write(self.running_config)

    def request_system_snapshot(self, parameters=None):
        """Request a system snapshot and verify completion.

        Issues the snapshot RPC call and polls device to verify completion.
        Handles RPC timeouts by switching to polling mode.

        Parameters include:
         - all-members
         - local
         - media
         - member
         - partition
         - slice

        Args:
            parameters (str, optional): Parameters to pass to the RPC call. Defaults to None.

        Raises:
            OSInstallError: If snapshot verification fails or times out.
        """
        command = "request system snapshot"
        if parameters is not None:
            command = f"{command} {parameters}"

        response = None
        rpc_timed_out = False

        try:
            log.debug("Host %s: Issuing RPC: %s", self.host, command)
            response = self.native.rpc.cli(command=command, format="text")
            log.debug("Host %s: snapshot RPC completed.", self.host)

        except RpcTimeoutError:
            log.debug("Host %s: snapshot RPC timed out; will poll device to verify.", self.host)
            rpc_timed_out = True

        except Exception as rpc_error:
            log.error("Host %s: Failed to request system snapshot (%s).", self.host, rpc_error)
            raise

        # Check if snapshot completed in the response (fast path)
        if response is not None and "filesystems were archived" in str(response):
            log.info("Host %s: Snapshot completed successfully (fast path).", self.host)
            return

        # If RPC timed out or response didn't indicate completion, poll to verify (slow path)
        if rpc_timed_out or response is None:
            log.debug("Host %s: Snapshot response unclear or timed out; polling device to verify.", self.host)
        self._wait_for_system_snapshot()

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
        if self._uptime is None:
            try:
                # Bust PyEZ's cached facts so a cold cache always reflects the live device.
                self.native.facts_refresh(keys="RE0")
                native_uptime_string = self.native.facts["RE0"]["up_time"]
            except (AttributeError, TypeError, KeyError):
                native_uptime_string = None

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
        if self._uptime_string is None:
            try:
                # Bust PyEZ's cached facts so a cold cache always reflects the live device.
                self.native.facts_refresh(keys="RE0")
                native_uptime_string = self.native.facts["RE0"]["up_time"]
            except (AttributeError, TypeError, KeyError):
                native_uptime_string = None

            if native_uptime_string is not None:
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

    @property
    def is_virtual_chassis(self) -> bool:
        """Check if device is in virtual-chassis mode."""
        if self._is_virtual_chassis is None:
            self._is_virtual_chassis = self.native.facts.get("vc_capable", False)

        return self._is_virtual_chassis

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

    def _validate_member_status(self):
        """Validate and log virtual-chassis member status.

        Checks re_info for:
        - Member count
        - Each member's status (should be 'OK')
        - Mastership state (master/backup)
        - Last reboot reason

        Returns:
            dict: Member status info indexed by member ID.

        Raises:
            OSInstallError: If any member status is not 'OK'.
        """
        re_info = self.native.facts.get("re_info", {}).get("default", {})
        if not re_info:
            log.warning("Host %s: No re_info available; cannot validate member status", self.host)
            return {}

        member_status = {}
        for member_id, member_info in re_info.items():
            if member_id == "default":
                continue

            status = member_info.get("status", "UNKNOWN")
            mastership = member_info.get("mastership_state", "UNKNOWN")
            reboot_reason = member_info.get("last_reboot_reason", "UNKNOWN")
            model = member_info.get("model", "UNKNOWN")

            member_status[member_id] = {
                "status": status,
                "mastership": mastership,
                "reboot_reason": reboot_reason,
                "model": model,
            }

            log.info(
                "Host %s: Member %s - Status: %s, Mastership: %s, Model: %s",
                self.host,
                member_id,
                status,
                mastership,
                model,
            )
            log.debug("Host %s: Member %s reboot reason: %s", self.host, member_id, reboot_reason)

            if status != "OK":
                log.error("Host %s: Member %s status is %s (expected OK)", self.host, member_id, status)
                raise OSInstallError(hostname=self.hostname, desired_boot="N/A")

        return member_status

    def _validate_post_install_state(self, expected_version):
        """Validate post-install state via re_info.

        Checks re_info for:
        - All members in 'OK' status
        - All members running expected version
        - Reboot reasons don't indicate failures

        Args:
            expected_version (str): Expected OS version after install.

        Raises:
            OSInstallError: If any member is not in expected state.
        """
        re_info = self.native.facts.get("re_info", {}).get("default", {})
        if not re_info:
            log.warning("Host %s: No re_info available for post-install validation", self.host)
            return

        for member_id, member_info in re_info.items():
            if member_id == "default":
                continue

            status = member_info.get("status", "UNKNOWN")
            reboot_reason = member_info.get("last_reboot_reason", "UNKNOWN")
            model = member_info.get("model", "UNKNOWN")

            if status != "OK":
                log.error(
                    "Host %s: Member %s status is %s (expected OK) after install",
                    self.host,
                    member_id,
                    status,
                )
                raise OSInstallError(hostname=self.hostname, desired_boot=expected_version)

            log.info(
                "Host %s: Member %s post-install state validated - Status: OK, Model: %s, Reboot reason: %s",
                self.host,
                member_id,
                model,
                reboot_reason,
            )

    def _is_multiple_device_setup(self) -> bool:
        """Check if device is in a multiple-device setup (virtual-chassis or chassis-cluster).

        Validates that:
        - Device is vc_capable
        - Multiple routing engines exist in re_info
        - All members have status 'OK'

        Returns:
            bool: True if device is part of a multiple-device setup, False otherwise.

        Raises:
            OSInstallError: If any member status is not 'OK'.
        """
        if not self.is_virtual_chassis:
            return False

        re_info = self.native.facts.get("re_info", {}).get("default", {})
        members = {k: v for k, v in re_info.items() if k != "default"}

        if len(members) <= 1:
            log.debug(
                "Host %s: vc_capable=True but only %d members; treating as single device", self.host, len(members)
            )
            return False

        log.info("Host %s: Detected multiple-device setup with %d members", self.host, len(members))
        self._validate_member_status()
        return True

    def _validate_and_capture_preinstall_state(self, image_name, checksum, hashing_algorithm):
        """Validate image and capture pre-install state.

        Args:
            image_name (str): Path to OS image file on device.
            checksum (str): Checksum of the image file.
            hashing_algorithm (str): Hash algorithm ('md5', 'sha1', 'sha256').

        Returns:
            tuple: (pre_uptime, pre_version)

        Raises:
            FileTransferError: If image file not found or checksum mismatch.
        """
        if not self.check_file_exists(image_name):
            raise FileTransferError(message=f"Image {image_name} not found")

        if not self.compare_file_checksum(checksum, image_name, hashing_algorithm):
            raise FileTransferError(message=f"Checksum mismatch for {image_name}")

        log.info("Host %s: Image verified - %s", self.host, image_name)

        self._uptime = None
        pre_uptime = self.uptime
        pre_version = self.os_version

        log.info("Host %s: Pre-install state - OS: %s, uptime: %ss", self.host, pre_version, pre_uptime)

        return pre_uptime, pre_version

    def _wait_and_verify_upgrade(self, pre_uptime, pre_version, image_name):
        """Wait for device reboot and verify OS version changed.

        Args:
            pre_uptime (int): Uptime before upgrade.
            pre_version (str): OS version before upgrade.
            image_name (str): Name of image being installed.

        Raises:
            OSInstallError: If OS version did not change after reboot.
        """
        self._wait_for_device_reboot(pre_uptime)
        log.info("Host %s: Device reconnected after reboot.", self.host)

        self._uptime = None
        post_version = self.os_version

        if post_version == pre_version:
            log.error(
                "Host %s: Device rebooted but OS version unchanged. Expected change from %s, still running %s",
                self.host,
                pre_version,
                post_version,
            )
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

        log.info(
            "Host %s: OS upgrade verified. Previous version: %s. Current version: %s",
            self.host,
            pre_version,
            post_version,
        )

    def _reboot_all_members_and_wait(self, pre_reboot_uptime):
        """Issue explicit reboot of all members and wait for reconnection.

        Args:
            pre_reboot_uptime (int): Uptime before reboot.

        Raises:
            ConnectClosedError or Exception: If reboot command fails or device doesn't reconnect.
        """
        log.info("Host %s: Issuing explicit reboot of all members", self.host)
        try:
            self.native.rpc.cli(command="request system reboot all-members", format="text")
            log.info("Host %s: Reboot all-members command issued", self.host)
        except ConnectClosedError:
            log.debug("Host %s: Connection closed during reboot command (expected)", self.host)
        except Exception as reboot_error:
            log.error("Host %s: Failed to issue reboot command: %s", self.host, reboot_error)
            raise

        try:
            self._wait_for_device_reboot(pre_reboot_uptime)
            log.info("Host %s: Device reconnected after all-members reboot", self.host)
        except Exception as wait_error:
            log.error("Host %s: Failed waiting for device after reboot: %s", self.host, wait_error)
            raise

    def _disruptive_install_single(self, image_name, checksum, hashing_algorithm, pre_uptime, pre_version):
        """Perform a disruptive OS installation on a single device.

        Args:
            image_name (str): Path to OS image file on device.
            checksum (str): Checksum of the image file.
            hashing_algorithm (str): Hash algorithm ('md5', 'sha1', 'sha256').
            pre_uptime (int): Uptime before upgrade.
            pre_version (str): OS version before upgrade.
        """
        log.info("Host %s: Installing software update with disruptive reboot (single device).", self.host)
        install_ok = self.sw.install(
            package=image_name,
            checksum=checksum,
            checksum_algorithm=hashing_algorithm,
            progress=True,
            validate=True,
            no_copy=True,
            reboot=True,
            timeout=3600,
        )

        self._wait_and_verify_upgrade(pre_uptime, pre_version, image_name)
        self._validate_post_install_state(self.os_version)

        if isinstance(install_ok, tuple):
            install_ok = install_ok[0]

        if not install_ok:
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

    def _disruptive_install_multiple(self, image_name, checksum, hashing_algorithm, pre_uptime, pre_version):
        """Perform a disruptive OS installation on multiple-device virtual-chassis.

        Includes explicit reboot of all members and snapshot of alternate partitions.

        Args:
            image_name (str): Path to OS image file on device.
            checksum (str): Checksum of the image file.
            hashing_algorithm (str): Hash algorithm ('md5', 'sha1', 'sha256').
            pre_uptime (int): Uptime before upgrade.
            pre_version (str): OS version before upgrade.
        """
        log.info("Host %s: Installing software update with disruptive reboot (multiple-device).", self.host)
        install_ok = self.sw.install(
            package=image_name,
            checksum=checksum,
            checksum_algorithm=hashing_algorithm,
            progress=True,
            validate=True,
            no_copy=True,
            reboot=True,
            timeout=3600,
        )

        self._wait_and_verify_upgrade(pre_uptime, pre_version, image_name)
        self._validate_post_install_state(self.os_version)

        if isinstance(install_ok, tuple):
            install_ok = install_ok[0]

        if not install_ok:
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

        self._uptime = None
        pre_reboot_uptime = self.uptime
        self._reboot_all_members_and_wait(pre_reboot_uptime)
        self.request_system_snapshot("slice alternate all-members")
        self._validate_post_install_state(self.os_version)

    def _non_disruptive_install_single(
        self, image_name, checksum, hashing_algorithm, issu, nssu, pre_uptime, pre_version
    ):
        """Perform a non-disruptive OS installation on a single device.

        Args:
            image_name (str): Path to OS image file on device.
            checksum (str): Checksum of the image file.
            hashing_algorithm (str): Hash algorithm ('md5', 'sha1', 'sha256').
            issu (bool): Whether to perform ISSU.
            nssu (bool): Whether to perform NSSU.
            pre_uptime (int): Uptime before upgrade.
            pre_version (str): OS version before upgrade.
        """
        log.info("Host %s: Installing software update using ISSU or NSSU (single device).", self.host)
        try:
            install_ok = self.sw.install(
                package=image_name,
                checksum=checksum,
                checksum_algorithm=hashing_algorithm,
                progress=True,
                validate=True,
                no_copy=True,
                reboot=False,
                issu=issu,
                nssu=nssu,
                timeout=3600,
            )
        except RpcError as rpc_error:
            if "reboot pending for software rollback" in str(rpc_error).lower():
                log.warning(
                    "Host %s: Device has pending reboot state; A manual reboot will be required to continue.",
                    self.host,
                )
                raise
        except ConnectClosedError:
            log.info(
                "Host %s: Connection closed during install (expected for device reboot). "
                "Waiting for device to come back online.",
                self.host,
            )

        self._wait_and_verify_upgrade(pre_uptime, pre_version, image_name)
        self._validate_post_install_state(self.os_version)

        if isinstance(install_ok, tuple):
            install_ok = install_ok[0]

        if not install_ok:
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

    def _non_disruptive_install_multiple(
        self, image_name, checksum, hashing_algorithm, issu, nssu, pre_uptime, pre_version
    ):
        """Perform a non-disruptive OS installation on multiple-device virtual-chassis.

        Includes explicit reboot of all members and snapshot of alternate partitions.

        Args:
            image_name (str): Path to OS image file on device.
            checksum (str): Checksum of the image file.
            hashing_algorithm (str): Hash algorithm ('md5', 'sha1', 'sha256').
            issu (bool): Whether to perform ISSU.
            nssu (bool): Whether to perform NSSU.
            pre_uptime (int): Uptime before upgrade.
            pre_version (str): OS version before upgrade.
        """
        log.info("Host %s: Installing software update using ISSU or NSSU (multiple-device).", self.host)
        try:
            install_ok = self.sw.install(
                package=image_name,
                checksum=checksum,
                checksum_algorithm=hashing_algorithm,
                progress=True,
                validate=True,
                no_copy=True,
                reboot=False,
                issu=issu,
                nssu=nssu,
                timeout=3600,
            )
        except RpcError as rpc_error:
            if "reboot pending for software rollback" in str(rpc_error).lower():
                log.warning("Host %s: Device has pending reboot state; clearing with reboot.", self.host)
                self._uptime = None
                pre_reboot_uptime = self.uptime
                try:
                    self.native.rpc.request_reboot()
                    log.info("Host %s: Reboot issued to clear pending state.", self.host)
                    self._wait_for_device_reboot(pre_reboot_uptime)
                    log.info("Host %s: Device rebooted and reconnected.", self.host)

                    if not self.check_file_exists(image_name):
                        raise FileTransferError(message=f"Image file {image_name} missing after reboot")
                    log.info("Host %s: Image file verified after reboot.", self.host)

                    log.info("Host %s: Retrying install after clearing pending state.", self.host)
                    install_ok = self.sw.install(
                        package=image_name,
                        checksum=checksum,
                        checksum_algorithm=hashing_algorithm,
                        progress=True,
                        validate=True,
                        no_copy=True,
                        reboot=False,
                        issu=issu,
                        nssu=nssu,
                        timeout=3600,
                    )
                except Exception as retry_error:
                    log.error("Host %s: Failed to clear pending state: %s", self.host, retry_error)
                    raise
            else:
                raise
        except ConnectClosedError:
            log.info(
                "Host %s: Connection closed during install (expected for device reboot). "
                "Waiting for device to come back online.",
                self.host,
            )

        self._wait_and_verify_upgrade(pre_uptime, pre_version, image_name)
        self._validate_post_install_state(self.os_version)

        if isinstance(install_ok, tuple):
            install_ok = install_ok[0]

        if not install_ok:
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

        self._uptime = None
        pre_reboot_uptime = self.uptime
        self._reboot_all_members_and_wait(pre_reboot_uptime)
        self.request_system_snapshot("slice alternate all-members")
        self._validate_post_install_state(self.os_version)

    def _disruptive_install(self, image_name, checksum, hashing_algorithm, reboot):
        """Perform a disruptive OS installation."""

    def install_os(self, image_name, checksum, reboot=True, hashing_algorithm="md5", issu=False, nssu=False) -> bool:
        """Install OS on device.

        Supports both disruptive and non-disruptive upgrades on single and multiple-device setups.
        Automatically detects virtual-chassis and applies all-members operations when needed.

        Args:
            image_name (str): Path to OS image file on device.
            checksum (str): Checksum of the image file.
            reboot (bool): Whether to reboot the device. Defaults to True. Ignored if nssu is True.
            hashing_algorithm (str): Hash algorithm ('md5', 'sha1', 'sha256'). Defaults to 'md5'.
            issu (bool): Whether to perform ISSU. Defaults to False.
            nssu (bool): Whether to perform NSSU. Defaults to False. When True, reboot is automatic.

        Returns:
            bool: True if upgrade successful.

        Raises:
            FileTransferError: If image file not found or checksum mismatch.
            OSInstallError: If upgrade fails.
        """
        pre_uptime, pre_version = self._validate_and_capture_preinstall_state(image_name, checksum, hashing_algorithm)

        is_multiple_device = self._is_multiple_device_setup()
        is_disruptive = not (issu or nssu or not reboot)

        if is_disruptive:
            if is_multiple_device:
                self._disruptive_install_multiple(image_name, checksum, hashing_algorithm, pre_uptime, pre_version)
            else:
                self._disruptive_install_single(image_name, checksum, hashing_algorithm, pre_uptime, pre_version)
        else:
            if is_multiple_device:
                self._non_disruptive_install_multiple(
                    image_name, checksum, hashing_algorithm, issu, nssu, pre_uptime, pre_version
                )
            else:
                self._non_disruptive_install_single(
                    image_name, checksum, hashing_algorithm, issu, nssu, pre_uptime, pre_version
                )

        if not reboot:
            log.info("Host %s: OS image %s boot options set. Reboot the device to apply", self.host, image_name)
            return True

        if not nssu:
            self.reboot(wait_for_reload=True)

        return True

    def open(self):
        """Open connection to device."""
        if not self.connected:
            self.native.open()

    def reboot(self, wait_for_reload=False, timeout=7200, confirm=None):
        """
        Reload the controller or controller pair.

        Args:
            wait_for_reload (bool): Whether the reboot method should wait for the device to come back up before returning. Defaults to False.
            timeout (int, optional): Time in seconds to wait for the device to return after reboot. Defaults to 2 hours.
            confirm (None): Not used. Deprecated since v0.17.0.

        Example:
            >>> device = JunosDevice(**connection_args)
            >>> device.reboot()
            >>>
        """
        if confirm is not None:
            warnings.warn("Passing 'confirm' to reboot method is deprecated.", DeprecationWarning)

        self._uptime = None
        original_uptime = self.uptime
        if original_uptime is None:
            raise CommandError(
                command="reboot",
                message="Could not determine pre-reboot uptime; refusing to wait for reload.",
            )
        self.sw.reboot(in_min=0)
        if wait_for_reload:
            self._wait_for_device_reboot(original_uptime, timeout=timeout)

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

    @staticmethod
    def _netloc(src: FileCopyModel) -> str:
        """Return host:port or just host from a FileCopyModel."""
        return f"{src.hostname}:{src.port}" if src.port else src.hostname

    @staticmethod
    def _source_path(src: FileCopyModel) -> str:
        """Return the file path from URL, using file_name if path is empty."""
        return src.path if src.path and src.path != "/" else f"/{src.file_name}"

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
