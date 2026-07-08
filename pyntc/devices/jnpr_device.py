"""Module for using a Juniper junOS device."""

import hashlib
import os
import re
import time
import warnings
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from jnpr.junos import Device as JunosNativeDevice
from jnpr.junos.exception import ConfigLoadError, RpcError, RpcTimeoutError
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

        On virtual-chassis, multi-RE, and cluster platforms, PyEZ returns a
        nested ``{member: {filesystem: info}}`` dict instead of the flat
        ``{filesystem: info}`` shape. The mount is resolved per member and the
        **minimum** free space across members is returned — an install needs
        room on every member.

        Args:
            file_system (str, optional): Target path. When ``None`` (the
                default), the probe uses ``_JUNOS_DEFAULT_FILE_SYSTEM``
                (``/var/tmp`` — the standard destination for ``fs.cp`` copies
                on Junos).

        Returns:
            int: Free bytes available on the resolved filesystem (the smallest
                member's value on multi-member platforms).

        Raises:
            FileSystemNotFoundError: When no mount point encloses ``file_system``
                on any member (i.e., not even ``/`` is present in
                ``storage_usage`` for that member).
            CommandError: When an ``avail`` format string cannot be parsed.
        """
        if file_system is None:
            file_system = _JUNOS_DEFAULT_FILE_SYSTEM

        usage = self.fs.storage_usage()
        # Flat entries always carry a "mount" key; on multi-member platforms
        # the top-level values are per-member {filesystem: info} dicts instead.
        is_nested = bool(usage) and all(isinstance(info, dict) and "mount" not in info for info in usage.values())
        member_groups = usage if is_nested else {"": usage}

        free_bytes = min(
            self._free_bytes_for_mount(filesystems, file_system, member=member)
            for member, filesystems in member_groups.items()
        )
        log.debug(
            "Host %s: %s bytes free (resolved from %s across %d member(s)).",
            self.host,
            free_bytes,
            file_system,
            len(member_groups),
        )
        return free_bytes

    def _free_bytes_for_mount(self, filesystems, file_system, member=""):
        """Resolve ``file_system`` within one member's storage output and return its free bytes."""
        best_info = None
        best_mount = None
        best_len = -1
        for _dev, info in filesystems.items():
            mount = info.get("mount")
            if not mount or not _mount_encloses_path(mount, file_system):
                continue
            if len(mount) > best_len:
                best_info = info
                best_mount = mount
                best_len = len(mount)

        if best_info is None:
            log.error(
                "Host %s: no mount encloses %s in storage_usage output%s.",
                self.host,
                file_system,
                f" for member {member}" if member else "",
            )
            raise FileSystemNotFoundError(hostname=self.host, command="show system storage")

        avail = best_info.get("avail", "")
        match = _JUNOS_AVAIL_FORMAT_RE.match(str(avail))
        if match is None:
            log.error(
                "Host %s: could not parse avail %r for mount %s%s.",
                self.host,
                avail,
                best_mount,
                f" on member {member}" if member else "",
            )
            raise CommandError(
                command="show system storage",
                message=f"Unable to parse available space {avail!r} for {best_mount}.",
            )
        size = float(match.group(1))
        multiplier = _JUNOS_SIZE_UNIT_MULTIPLIERS[match.group(2).upper()]
        return int(size * multiplier)

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

    def _wait_for_device_reboot(self, original_uptime, timeout=7200, is_multiple=False):
        """Block until the device reboots and accepts a fresh connection.

        Drops the existing NETCONF session and polls for the device to come back.
        The reboot is considered complete when a new connection succeeds and the
        device reports an uptime lower than ``original_uptime`` (i.e., it has
        booted since the reboot was issued).

        For multi-device setups (virtual-chassis, chassis-cluster), checks that all
        members have rebooted by verifying no members in re_info are in pending state.

        The pre-reboot session must be discarded first: once the device restarts,
        PyEZ still reports it as connected even though the transport is dead, so it
        is closed here to force each probe to establish a fresh connection.

        Args:
            original_uptime (int): Device uptime in seconds captured before the reboot.
            timeout (int, optional): Max seconds to wait for the device to return. Defaults to 2 hours.
            is_multiple (bool, optional): Whether device is in multi-device configuration. Defaults to False.
        """
        start = time.time()

        # Drop the pre-reboot NETCONF session so subsequent probes can't read from
        # a stale connection PyEZ still reports as connected.
        try:
            self.close()
        except Exception as close_exc:  # pylint: disable=broad-exception-caught
            log.debug("Host %s: Pre-reboot disconnect raised %s (ignored).", self.host, close_exc)

        # Give the device time to boot before polling (avoid hammering a device that's still starting up)
        log.info("Host %s: Waiting 180 seconds for device to boot before polling...", self.host)
        time.sleep(180)

        while time.time() - start < timeout:
            try:
                self.open()
                self._uptime = None
                current_uptime = self.uptime

                if is_multiple:
                    # For multi-device, check that no members are in pending state
                    self.native.facts_refresh()
                    re_info = self.native.facts.get("re_info", {})
                    # Virtual-chassis structure: members are under re_info['default']
                    members = re_info.get("default", {})
                    pending_members = [
                        name
                        for name, info in members.items()
                        if name != "default" and isinstance(info, dict) and info.get("status") == "pending"
                    ]
                    if pending_members:
                        log.debug(
                            "Host %s: Members still pending reboot: %s; still waiting.",
                            self.host,
                            pending_members,
                        )
                    elif current_uptime is not None and current_uptime < original_uptime:
                        log.info(
                            "Host %s: Device rebooted (uptime %ss < pre-reboot %ss).",
                            self.host,
                            current_uptime,
                            original_uptime,
                        )
                        return
                else:
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
            time.sleep(30)

        raise RebootTimeoutError(hostname=self.hostname, wait_time=timeout)

    def _wait_for_nssu_completion(self, target_version, timeout=3600, interval=60):
        """Wait for all members to complete NSSU and run target version.

        Polls device to verify all members are running the same (target) software version.
        Used to ensure NSSU/ISSU has fully completed before proceeding.

        Args:
            target_version (str): Target software version (e.g., "15.1R7-S2").
            timeout (int, optional): Max seconds to wait. Defaults to 1 hour.
            interval (int, optional): Seconds between version checks. Defaults to 60.

        Raises:
            OSInstallError: When all members don't match target version within timeout.
        """
        start = time.time()

        while time.time() - start < timeout:
            try:
                members_versions = self._get_all_members_version()
                if not members_versions:
                    log.debug("Host %s: Could not retrieve member versions; will retry.", self.host)
                    time.sleep(interval)
                    continue

                # Check if all members are running the target version
                all_match = all(v == target_version for v in members_versions.values())
                mismatched = {m: v for m, v in members_versions.items() if v != target_version}

                if all_match:
                    log.info(
                        "Host %s: All members running target version %s.",
                        self.host,
                        target_version,
                    )
                    return

                log.debug(
                    "Host %s: Members not all on target version %s. Still waiting on: %s",
                    self.host,
                    target_version,
                    mismatched,
                )

            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.debug("Host %s: Version check failed (%s); will retry.", self.host, exc)

            time.sleep(interval)

        log.error(
            "Host %s: Not all members reached target version %s within %s seconds.",
            self.host,
            target_version,
            timeout,
        )
        raise OSInstallError(hostname=self.hostname, desired_boot=target_version)

    def _get_all_members_version(self):
        """Get software version running on all members.

        Parses `show version all-members` output to extract version for each member.

        Returns:
            dict: Member IDs mapped to their running version. Example:
                {'0': '15.1R7-S2', '1': '12.3R12-S10'}
        """
        try:
            version_output = self.show("show version all-members")
            members_versions = {}
            current_member = None

            for line in version_output.split("\n"):
                # Detect member header (fpc0:, fpc1:, etc.)
                if line.startswith("fpc") and line.endswith(":"):
                    current_member = line.split("fpc")[1].rstrip(":")
                    members_versions[current_member] = None

                # Extract version from JUNOS Base OS Software Suite line
                if current_member and "JUNOS Base OS Software Suite" in line:
                    # Extract version from format: JUNOS Base OS Software Suite [15.1R7-S2]
                    match = re.search(r"\[([^\]]+)\]", line)
                    if match:
                        members_versions[current_member] = match.group(1)

            log.debug("Host %s: Members versions: %s", self.host, members_versions)
            return members_versions
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error("Host %s: Failed to get all members version: %s", self.host, exc)
            return {}

    def _verify_install_version(self, target_version, is_multiple):
        """Verify that the target version is running after install/reboot.

        Args:
            target_version (str): The expected version (e.g., "15.1R7-S2").
            is_multiple (bool): Whether this is a multi-device setup.

        Raises:
            OSInstallError: If the target version is not running on any member/device.
        """
        if is_multiple:
            members_versions = self._get_all_members_version()
            if not members_versions:
                log.warning(
                    "Host %s: Could not verify member versions after install; proceeding without verification",
                    self.host,
                )
                return

            mismatched = [member for member, version in members_versions.items() if version != target_version]
            if mismatched:
                log.error(
                    "Host %s: Version mismatch after install. Expected %s, got %s",
                    self.host,
                    target_version,
                    members_versions,
                )
                raise OSInstallError(hostname=self.hostname, desired_boot=target_version)

            log.info("Host %s: All members running target version %s", self.host, target_version)
        else:
            # For single device, check facts
            self.native.facts_refresh()
            current_version = self.native.facts.get("version", "")
            if current_version != target_version:
                log.error(
                    "Host %s: Version mismatch after install. Expected %s, got %s",
                    self.host,
                    target_version,
                    current_version,
                )
                raise OSInstallError(hostname=self.hostname, desired_boot=target_version)

            log.info("Host %s: Device running target version %s", self.host, target_version)

    def _request_system_reboot_all_members(self):
        """Issue system reboot command for all members using RPC CLI.

        Used for disruptive multi-member OS upgrades where both members reboot together.
        """
        try:
            log.info("Host %s: Issuing 'request system reboot all-members' command", self.host)
            response = self.native.rpc.cli(command="request system reboot all-members")
            log.debug("Host %s: Reboot command response: %s", self.host, response)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error("Host %s: Failed to issue reboot command: %s", self.host, exc)
            raise

    def _validate_multiple_device(self):
        """Check if device is in virtual-chassis or chassis-cluster configuration.

        Inspects re_info from PyEZ facts to determine if multiple members are present.

        Returns:
            bool: True if multiple members are present, False otherwise.
        """
        try:
            self.native.facts_refresh()
            re_info = self.native.facts.get("re_info", {})

            # Virtual-chassis structure: {'default': {'0': {...}, '1': {...}, 'default': {...}}}
            # Count members excluding the 'default' key itself
            if "default" in re_info and isinstance(re_info["default"], dict):
                members = {k: v for k, v in re_info["default"].items() if k != "default"}
                is_multiple = len(members) > 1
                log.info("Host %s: Multiple device configuration detected: %s", self.host, is_multiple)
                return is_multiple

            log.info("Host %s: Multiple device configuration detected: False", self.host)
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("Host %s: Could not validate multiple devices: %s", self.host, exc)
            return False

    def _wait_for_system_snapshot(self, timeout=900, interval=30):
        """Poll device to verify system snapshot completion.

        Periodically checks ``show system snapshot media internal`` to verify the snapshot
        was successfully taken. Used when the ``request system snapshot`` RPC times out.

        Args:
            timeout (int, optional): Max seconds to wait for snapshot verification. Defaults to 900 (15 minutes).
            interval (int, optional): Seconds between verification polls. Defaults to 30 seconds.

        Raises:
            TimeoutError: When the snapshot verification does not complete within the timeout.
        """
        log.info(
            "Host %s: Polling to verify system snapshot completion (timeout: %s seconds, interval: %s seconds)",
            self.host,
            timeout,
            interval,
        )
        start = time.time()

        # Give the snapshot time to complete before polling
        log.info("Host %s: Waiting 180 seconds for snapshot to complete before polling...", self.host)
        time.sleep(180)

        while time.time() - start < timeout:
            try:
                output = self.native.cli("show system snapshot media internal")
                # Check for actual snapshot success: "Creation date:" indicates snapshots exist
                # and timestamps indicate they were recently created
                if "Creation date:" in output:
                    log.info("Host %s: System snapshot verified (snapshots with creation dates found).", self.host)
                    return
                log.debug("Host %s: Snapshot verification in progress; will retry.", self.host)

            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.debug("Host %s: Snapshot verification poll failed (%s); will retry.", self.host, exc)

            time.sleep(interval)

        log.error("Host %s: System snapshot did not complete within %s seconds.", self.host, timeout)
        raise TimeoutError(f"System snapshot did not complete within {timeout} seconds on {self.hostname}")

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
            TimeoutError: When the snapshot verification does not complete within the timeout.
        """
        command = "request system snapshot"
        if parameters is not None:
            command = f"{command} {parameters}"

        response = None
        rpc_timed_out = False

        try:
            log.info("Host %s: Issuing snapshot RPC: %s", self.host, command)
            response = self.native.rpc.cli(command=command, format="text")
            log.info("Host %s: Snapshot RPC response: %s", self.host, response)

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

    def install_os(self, image_name, checksum, reboot=True, hashing_algorithm="md5", nssu=False, issu=False):  # pylint: disable=too-many-positional-arguments,too-many-branches
        """Install OS on device and reboot.

        For multi-device setups (virtual-chassis, chassis-cluster), supports NSSU/ISSU
        upgrades and system snapshots after reboot.

        Args:
            image_name (str): Name of image.
            checksum (str): The checksum of the file.
            reboot (bool): Whether to reboot the device after setting the boot options. Defaults to True.
            hashing_algorithm (str): The hashing algorithm to use. Valid values are 'md5', 'sha1', and 'sha256'. Defaults to 'md5'.
            nssu (bool): Enable Nonstop Software Upgrade. Defaults to False.
            issu (bool): Enable In-Service Software Upgrade. Defaults to False.

        Raises:
            ValueError: When both nssu and issu are True (mutually exclusive).
        """
        if nssu and issu:
            raise ValueError("nssu and issu are mutually exclusive; only one can be True")

        is_multiple = self._validate_multiple_device()

        install_kwargs = {
            "package": image_name,
            "checksum": checksum,
            "checksum_algorithm": hashing_algorithm,
            "progress": True,
            "validate": True,
            "no_copy": True,
            "timeout": 3600,
        }

        # Add NSSU/ISSU parameters for multi-device setups
        if is_multiple:
            if nssu:
                install_kwargs["nssu"] = True
                log.info("Host %s: NSSU enabled for multi-device upgrade", self.host)
            elif issu:
                install_kwargs["issu"] = True
                log.info("Host %s: ISSU enabled for multi-device upgrade", self.host)

        install_result = self.sw.install(**install_kwargs)

        # Sometimes install() returns a tuple of (ok, msg). Other times it returns a single bool
        install_msg = None
        if isinstance(install_result, tuple):
            install_ok, install_msg = install_result[0], install_result[1]
        else:
            install_ok = install_result

        log.info("Host %s: install_ok result: %s (type: %s)", self.host, install_ok, type(install_result).__name__)
        if install_msg:
            log.debug("Host %s: install message: %s", self.host, install_msg)

        # Check if reboot is required (indicated by specific message in output)
        reboot_required = install_msg and "A reboot is required" in str(install_msg)

        if not install_ok and not reboot_required:
            log.error(
                "Host %s: SW install failed for image %s. Device is in undefined state.",
                self.host,
                image_name,
            )
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name)

        if not reboot:
            if reboot_required:
                raise OSInstallError(hostname=self.hostname, desired_boot=image_name)
            log.info("Host %s: OS image %s boot options set. Reboot the device to apply", self.host, image_name)
            return True

        log.info("Host %s: Rebooting device to apply OS image %s", self.host, image_name)
        self._uptime = None
        original_uptime = self.uptime

        if original_uptime is None:
            raise CommandError(
                command="install_os",
                message="Could not determine pre-reboot uptime; refusing to reboot.",
            )

        # Issue reboot command based on device configuration
        if is_multiple:
            self._request_system_reboot_all_members()
        else:
            self.sw.reboot(in_min=0)

        self._wait_for_device_reboot(original_uptime, is_multiple=is_multiple)

        # Extract target version from image name for verification
        # Matches formats: 15.1R7-S2, 20.4R3, 21.4X38-D10, 18.4R2.7, etc.
        match = re.search(r"(\d+\.\d+[A-Z]+\d+(?:\.\d+)?(?:[-][A-Z]+\d+)?)", image_name)
        target_version = match.group(1) if match else None

        # For NSSU/ISSU on multi-device, wait for all members to reach target version before snapshot
        if (nssu or issu) and is_multiple:
            if target_version:
                log.info(
                    "Host %s: Waiting for all members to complete %s upgrade to version %s",
                    self.host,
                    "NSSU" if nssu else "ISSU",
                    target_version,
                )
                self._wait_for_nssu_completion(target_version)
            else:
                log.warning(
                    "Host %s: Could not extract version from image name %s; skipping NSSU/ISSU completion wait",
                    self.host,
                    image_name,
                )

        # Perform system snapshot after reboot/upgrade
        snapshot_params = "slice alternate all-members" if is_multiple else "slice alternate"
        self.request_system_snapshot(parameters=snapshot_params)

        # Verify the install was successful by checking the running version
        if target_version:
            self._verify_install_version(target_version, is_multiple)
        else:
            log.warning(
                "Host %s: Could not extract version from image name %s; skipping post-reboot version verification",
                self.host,
                image_name,
            )

        log.info("Host %s: OS image %s installed successfully.", self.host, image_name)
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

        # Issue the file-copy RPC directly rather than through PyEZ ``fs.cp``,
        # which wraps it in a bare ``except`` and returns False — discarding the
        # device's actual error message. A successful reply may be the bool True
        # (empty rpc-reply) or an XML element; only an exception means failure.
        try:
            self.native.rpc.file_copy(source=source_url, destination=dest, dev_timeout=src.timeout)
        except RpcError as exc:
            log.error("Host %s: file copy from %s failed: %s", self.host, src.clean_url, exc)
            raise FileTransferError(message=f"Unable to copy file from remote url {src.clean_url}: {exc}") from exc

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
