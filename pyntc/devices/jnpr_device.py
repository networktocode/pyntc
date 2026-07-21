"""Module for using a Juniper junOS device."""

import hashlib
import os
import re
import shlex
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
from jnpr.junos.utils.start_shell import StartShell
from jnpr.junos.utils.sw import SW as JunosNativeSW

from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs
from pyntc.devices.tables.jnpr.loopback import LoopbackTable  # pylint: disable=no-name-in-module
from pyntc.errors import (
    CommandError,
    CommandListError,
    DeviceNotActiveError,
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

# URL schemes the FreeBSD ``fetch`` binary on Junos can download. Other
# schemes (e.g., scp) go through the ``file copy`` RPC instead.
_JUNOS_FETCH_SCHEMES = {"ftp", "http", "https"}

# Head start given to reboots and snapshots before the first status poll —
# probing earlier burns round-trips against a device that cannot be ready yet.
_JUNOS_POLL_WARMUP_SECONDS = 180

# Extracts a Junos version from an install image filename.
# Matches formats: 15.1R7-S2, 20.4R3, 21.4X38-D10, 18.4R2.7, etc.
_JUNOS_VERSION_RE = re.compile(r"(\d+\.\d+[A-Z]+\d+(?:\.\d+)?(?:[-][A-Z]+\d+)?)")

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
        self._is_chassis_cluster = None

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
        # Multi-member platforms nest dicts; single-member platforms are flat with "mount" key.
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
            timeout (int, optional): Max seconds to poll for the device to return,
                counted after the initial warm-up delay. Defaults to 2 hours.
            is_multiple (bool, optional): Whether device is in multi-device configuration. Defaults to False.
        """
        # Close stale session; PyEZ may report it as connected even after reboot.
        try:
            self.close()
        except Exception as close_exc:  # pylint: disable=broad-exception-caught
            log.debug("Host %s: Pre-reboot disconnect raised %s (ignored).", self.host, close_exc)

        # Give the device time to boot before polling (avoid hammering a device that's still starting up)
        log.info(
            "Host %s: Waiting %s seconds for device to boot before polling...",
            self.host,
            _JUNOS_POLL_WARMUP_SECONDS,
        )
        time.sleep(_JUNOS_POLL_WARMUP_SECONDS)

        # Start the clock after the warm-up so ``timeout`` is the real polling window.
        start = time.time()

        while time.time() - start < timeout:
            try:
                self.open()
                self._uptime = None
                current_uptime = self.uptime

                if is_multiple and (pending_members := self._pending_reboot_members()):
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

    def _pending_reboot_members(self):
        """Return VC member names whose re_info status is still "pending"."""
        # Scoped refresh for re_info only; full refresh would re-collect all facts (many RPCs).
        try:
            self.native.facts_refresh(keys="re_info")
        except RuntimeError:
            # PyEZ only supports scoped refresh with fact_style="new"; fall back to full refresh.
            self.native.facts_refresh()
        # Virtual-chassis structure: members are under re_info['default']
        members = self.native.facts.get("re_info", {}).get("default", {})
        return [
            name
            for name, info in members.items()
            if name != "default" and isinstance(info, dict) and info.get("status") == "pending"
        ]

    def _vc_member_count(self):
        """Count VC members from the currently cached re_info facts (no refresh).

        Only the virtual-chassis ``re_info['default']`` structure is recognized;
        other layouts (e.g., SRX chassis-cluster) yield 0.
        """
        members = self.native.facts.get("re_info", {}).get("default", {})
        return len([name for name in members if name != "default"])

    def _detect_chassis_cluster(self):
        """Detect if device is an SRX chassis-cluster by checking srx_cluster in facts.

        SRX chassis-cluster stores cluster info under the 'srx_cluster' fact key.
        Returns True if srx_cluster information is found in facts.
        """
        srx_cluster_info = self.native.facts.get("srx_cluster")
        is_chassis_cluster = bool(srx_cluster_info)
        log.debug(
            "Host %s: Checking for SRX chassis-cluster; srx_cluster fact=%s, result=%s",
            self.host,
            srx_cluster_info,
            is_chassis_cluster,
        )
        return is_chassis_cluster

    def _is_srx3xx(self):
        """Return True if device is SRX3xx platform."""
        if self._model is None:
            self._model = self.native.facts.get("model")
        if self._model and "srx3" in str(self._model).lower():
            return True
        return False

    def _wait_for_nssu_completion(self, target_version, timeout=3600, interval=60, expected_members=None):
        """Wait for all members to complete NSSU/ISSU and run target version.

        Polls device to verify all members are running the same (target) software version.
        The in-service upgrade reboots each member itself (the old master goes down right
        as the install RPC returns), so each poll reconnects if the session dropped.

        Args:
            target_version (str): Target software version (e.g., "15.1R7-S2").
            timeout (int, optional): Max seconds to wait. Defaults to 1 hour.
            interval (int, optional): Seconds between version checks. Defaults to 60.
            expected_members (int, optional): Number of members that must report a
                version before the result is trusted. Guards against declaring
                success while a member is mid-reboot and absent from
                ``show version all-members``. When ``None``, any non-empty result
                is compared as-is.

        Raises:
            OSInstallError: When all members don't match target version within timeout.
        """
        start = time.time()

        # Close stale session before poll; PyEZ may report it as connected after reboot.
        try:
            self.close()
        except Exception as close_exc:  # pylint: disable=broad-exception-caught
            log.debug("Host %s: Pre-poll disconnect raised %s (ignored).", self.host, close_exc)

        while time.time() - start < timeout:
            try:
                self.open()
                members_versions = self._get_all_members_version()
                mismatched = {m: v for m, v in members_versions.items() if v != target_version}

                if not members_versions:
                    log.debug("Host %s: Could not retrieve member versions; will retry.", self.host)
                elif expected_members is not None and len(members_versions) < expected_members:
                    log.debug(
                        "Host %s: Only %s of %s members reporting a version; still waiting.",
                        self.host,
                        len(members_versions),
                        expected_members,
                    )
                elif not mismatched:
                    log.info(
                        "Host %s: All members running target version %s.",
                        self.host,
                        target_version,
                    )
                    return
                else:
                    log.debug(
                        "Host %s: Members not all on target version %s. Still waiting on: %s",
                        self.host,
                        target_version,
                        mismatched,
                    )

            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.debug("Host %s: Version check failed (%s); will retry.", self.host, exc)
                self.native.connected = False

            time.sleep(interval)

        log.error(
            "Host %s: Not all members reached target version %s within %s seconds.",
            self.host,
            target_version,
            timeout,
        )
        raise OSInstallError(hostname=self.hostname, desired_boot=target_version)

    def _get_chassis_cluster_versions(self):
        """Get software version from both nodes in SRX chassis-cluster.

        Parses 'show version' output to extract version for each node, returning
        node numbers as keys for consistency with facts and verification.

        Returns:
            dict: Node numbers mapped to their running version. Example:
                {'0': '21.4R3-S5.3', '1': '21.4R3-S5.3'}
        """
        try:
            version_output = self.show("show version")
            node_versions = {}
            current_node = None

            for line in version_output.splitlines():
                line = line.strip()

                # Detect node header (node0:, node1:, etc.)
                if line.startswith("node") and line.endswith(":"):
                    current_node = line.rstrip(":")
                    node_versions[current_node] = None
                    continue

                if current_node is None or node_versions[current_node] is not None:
                    continue

                # Extract version from "Junos: <version>" line
                if line.startswith("Junos:"):
                    tokens = line.split(":", 1)[1].split()
                    if tokens:
                        node_versions[current_node] = tokens[0]

            # Convert node names (node0, node1) to node numbers (0, 1) for consistency
            numbered_versions = {}
            for node_name, version in node_versions.items():
                if node_name.startswith("node"):
                    node_num = node_name.replace("node", "")
                    numbered_versions[node_num] = version
                else:
                    numbered_versions[node_name] = version

            log.debug("Host %s: SRX chassis-cluster node versions: %s", self.host, numbered_versions)
            return numbered_versions
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error("Host %s: Failed to get chassis-cluster versions: %s", self.host, exc)
            return {}

    def _get_all_members_version(self):
        """Get software version running on all members.

        Parses `show version all-members` output to extract version for each member.
        Handles different Junos release formats: Junos 13.2+ prints a dedicated
        `Junos: <version>` line, while older releases only list packages in format
        `JUNOS <package> [<version>]`. Takes the first version token to drop
        qualifiers like "15.1R7-S2 Limited" that would break exact-match comparison.

        Returns:
            dict: Member IDs mapped to their running version. Example:
                {'0': '15.1R7-S2', '1': '12.3R12-S10'}
        """
        try:
            version_output = self.show("show version all-members")
            members_versions = {}
            current_member = None

            for line in (raw_line.strip() for raw_line in version_output.splitlines()):
                if line.startswith("fpc") and line.endswith(":"):
                    current_member = line.split("fpc")[1].rstrip(":")
                    members_versions[current_member] = None
                    continue

                if current_member is None or members_versions[current_member] is not None:
                    continue

                if line.startswith("Junos:"):
                    tokens = line.split(":", 1)[1].split()
                    if tokens:
                        members_versions[current_member] = tokens[0]
                elif line.startswith("JUNOS"):
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
            is_multiple (bool): Whether this is a multi-device setup (virtual-chassis).

        Raises:
            OSInstallError: If the target version is not running on any member/device.
        """
        # Check if this is SRX chassis-cluster (multiple nodes but not virtual-chassis)
        is_chassis_cluster = self._is_chassis_cluster or self._detect_chassis_cluster()

        if is_multiple and not is_chassis_cluster:
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
        elif is_chassis_cluster:
            # SRX chassis-cluster: verify both nodes running target version
            members_versions = self._get_chassis_cluster_versions()
            if not members_versions:
                log.warning(
                    "Host %s: Could not verify chassis-cluster node versions after install; proceeding without verification",
                    self.host,
                )
                return

            mismatched = [node for node, version in members_versions.items() if version != target_version]
            if mismatched:
                log.error(
                    "Host %s: Version mismatch after install. Expected %s, got %s",
                    self.host,
                    target_version,
                    members_versions,
                )
                raise OSInstallError(hostname=self.hostname, desired_boot=target_version)

            log.info("Host %s: All chassis-cluster nodes running target version %s", self.host, target_version)
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
        """Check if device is in a multi-member configuration.

        Inspects re_info from PyEZ facts to determine if multiple members are present.
        Currently only the virtual-chassis ``re_info['default']`` structure is
        recognized; chassis-cluster (SRX) layouts are not yet detected.

        Returns:
            bool: True if multiple members are present, False otherwise.
        """
        try:
            self.native.facts_refresh()
            re_info = self.native.facts.get("re_info", {})
            log.debug("Host %s: re_info keys: %s", self.host, list(re_info.keys()))

            # VC members nested under re_info['default'], excluding the 'default' key itself.
            if "default" in re_info and isinstance(re_info["default"], dict):
                members = {k: v for k, v in re_info["default"].items() if k != "default"}
                is_multiple = len(members) > 1
                log.debug(
                    "Host %s: Found re_info['default'] with members: %s, is_multiple=%s",
                    self.host,
                    list(members.keys()),
                    is_multiple,
                )
                log.info("Host %s: Multiple device configuration detected: %s", self.host, is_multiple)
                return is_multiple

            log.debug("Host %s: re_info['default'] not found or invalid structure", self.host)
            log.info("Host %s: Multiple device configuration detected: False", self.host)
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("Host %s: Could not validate multiple devices: %s", self.host, exc)
            return False

    def _get_icu_redundancy_groups(self):
        """Get list of redundancy group numbers from chassis-cluster configuration.

        Parses 'show configuration chassis cluster' output to find all configured
        redundancy groups.

        Returns:
            list: Redundancy group numbers (e.g., [0, 1]) or empty list if not a chassis-cluster.
        """
        try:
            output = self.show("show configuration chassis cluster")
            if "syntax error" in output.lower() or "unknown command" in output.lower():
                return []

            redundancy_groups = []
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("redundancy-group "):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            group_num = int(parts[1].rstrip("{"))
                            if group_num not in redundancy_groups:
                                redundancy_groups.append(group_num)
                        except ValueError:
                            pass

            log.debug("Host %s: Found redundancy groups: %s", self.host, sorted(redundancy_groups))
            return sorted(redundancy_groups)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error("Host %s: Failed to get redundancy groups: %s", self.host, exc)
            return []

    def _get_node_redundancy_status(self, node, redundancy_group):
        """Get a node's status (primary/secondary) for a specific redundancy group.

        Parses 'show chassis cluster status' output to find the node's role in the given RG.

        Args:
            node (str): Node name (e.g., 'node0', 'node1')
            redundancy_group (int): Redundancy group number

        Returns:
            str: Node status ('primary', 'secondary') or empty string if not found.
        """
        try:
            output = self.show("show chassis cluster status")
            log.debug("Host %s: Parsing cluster status for %s in RG %d", self.host, node, redundancy_group)
            current_group = None

            for line in output.splitlines():
                line = line.strip()

                if line.startswith("Redundancy group:"):
                    try:
                        parts = line.split(",")[0].split()
                        current_group = int(parts[2])
                        log.debug("Host %s: Found RG header: %d", self.host, current_group)
                    except (ValueError, IndexError):
                        pass
                    continue

                if current_group == redundancy_group:
                    if line.startswith(node):
                        log.debug("Host %s: Found node line for RG %d: %s", self.host, redundancy_group, line)
                        parts = line.split()
                        if len(parts) >= 3:
                            status = parts[2]
                            log.debug(
                                "Host %s: Extracted status for %s in RG %d: %s",
                                self.host,
                                node,
                                redundancy_group,
                                status,
                            )
                            return status

            log.warning(
                "Host %s: Could not find status for %s in RG %d",
                self.host,
                node,
                redundancy_group,
            )
            return ""
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error(
                "Host %s: Failed to get status for node %s in RG %d: %s",
                self.host,
                node,
                redundancy_group,
                exc,
            )
            return ""

    def _failover_redundancy_group(self, redundancy_group, target_node):
        """Failover a redundancy group to target node.

        Args:
            redundancy_group (int): Redundancy group number
            target_node (str): Target node name (e.g., 'node0')

        Raises:
            CommandError: If failover fails
        """
        try:
            # Extract node number from name (node0 -> 0, node1 -> 1)
            node_num = target_node.replace("node", "")
            command = f"request chassis cluster failover redundancy-group {redundancy_group} node {node_num}"

            log.info(
                "Host %s: Failing over RG %d to %s",
                self.host,
                redundancy_group,
                target_node,
            )
            log.debug("Host %s: Failover command: %s", self.host, command)

            response = self.native.rpc.cli(format="text", command=command)
            log.info("Host %s: Failover RPC response for RG %d:\n%s", self.host, redundancy_group, response)
            log.info("Host %s: Failover succeeded for RG %d to %s", self.host, redundancy_group, target_node)
            time.sleep(30)  # Allow cluster to stabilize after failover
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error(
                "Host %s: Failover failed for RG %d to %s: %s",
                self.host,
                redundancy_group,
                target_node,
                exc,
            )
            raise CommandError(
                command=f"request chassis cluster failover redundancy-group {redundancy_group} node {node_num}",
                message=f"Failed to failover RG {redundancy_group} to {target_node}: {exc}",
            ) from exc

    def _initiate_issu_upgrade(self, image_name, is_icu=False, no_validate=False):
        """Issue in-service upgrade command (ISSU or ICU) via CLI.

        Builds command dynamically:
        - Base: request system software in-service-upgrade {image_name}
        - If is_icu: append "no-sync" (ICU-specific)
        - If no_validate: append "no-validate" (optional for both)

        Args:
            image_name (str): Full path to image on device
            is_icu (bool): If True, add "no-sync" flag for ICU. Defaults to False.
            no_validate (bool): If True, add "no-validate" flag. Defaults to False.

        Raises:
            OSInstallError: On RPC command failures (non-timeout errors).

        Returns:
            RPC response text if command succeeds, None if RpcTimeoutError occurs
            (timeout is expected during device reboot and is not treated as an error).
        """
        flags = []
        if is_icu:
            flags.append("no-sync")
        if no_validate:
            flags.append("no-validate")

        command = f"request system software in-service-upgrade {image_name}"
        if flags:
            command = f"{command} {' '.join(flags)}"

        upgrade_type = "ICU" if is_icu else "ISSU"
        log.info("Host %s: Initiating %s upgrade", self.host, upgrade_type)
        log.debug("Host %s: Command: %s", self.host, command)

        rpc_response = None
        original_timeout = self.native.timeout
        try:
            if is_icu:
                self.native.timeout = 1800
                log.debug("Host %s: Increased RPC timeout to 30 minutes for ICU upgrade", self.host)
            rpc_response = self.native.rpc.cli(command=command)
            if rpc_response is not None:
                response_text = str(rpc_response).strip()
                log.info("Host %s: %s response received:\n%s", self.host, upgrade_type, response_text)
            else:
                log.info("Host %s: %s command accepted (no immediate response)", self.host, upgrade_type)
        except RpcTimeoutError:
            log.info(
                "Host %s: RPC timeout during %s upgrade — device initiated reboot (expected behavior)",
                self.host,
                upgrade_type,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error(
                "Host %s: %s command failed with error:\n%s\nCommand was: %s", self.host, upgrade_type, exc, command
            )
            raise OSInstallError(hostname=self.hostname, desired_boot=image_name) from exc
        finally:
            self.native.timeout = original_timeout

        return rpc_response

    def _wait_for_system_snapshot(self, timeout=3600, interval=30):
        """Poll device to verify system snapshot completion.

        Periodically checks ``show system snapshot media internal`` to verify the snapshot
        was successfully taken. Used when the ``request system snapshot`` RPC times out.

        Args:
            timeout (int, optional): Max seconds to poll for snapshot verification,
                counted after the initial warm-up delay. Defaults to 3600 (60 minutes);
                field-observed all-members alternate-slice snapshots on a 2-member
                EX3300 VC have taken 25-35+ minutes.
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
        # Give the snapshot time to complete before polling
        log.info(
            "Host %s: Waiting %s seconds for snapshot to complete before polling...",
            self.host,
            _JUNOS_POLL_WARMUP_SECONDS,
        )
        time.sleep(_JUNOS_POLL_WARMUP_SECONDS)

        # Start the clock after the warm-up so ``timeout`` is the real polling window.
        start = time.time()

        while time.time() - start < timeout:
            try:
                output = self.native.cli("show system snapshot media internal")
                # "Creation date:" indicates recent snapshot completion.
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

        try:
            log.info("Host %s: Issuing snapshot RPC: %s", self.host, command)
            response = self.native.rpc.cli(command=command, format="text")
            log.info("Host %s: Snapshot RPC response: %s", self.host, response)

        except RpcTimeoutError:
            log.debug("Host %s: snapshot RPC timed out; will poll device to verify.", self.host)

        except Exception as rpc_error:
            log.error("Host %s: Failed to request system snapshot (%s).", self.host, rpc_error)
            raise

        # Check if snapshot completed in the response (fast path)
        if response is not None and "filesystems were archived" in str(response):
            log.info("Host %s: Snapshot completed successfully (fast path).", self.host)
            return

        # Response unclear or RPC timed out; poll to verify (slow path)
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

    def _install_os_icu(
        self,
        image_name,
        checksum,
        reboot=True,
        hashing_algorithm="md5",
        validate=False,
        snapshot=False,
    ):  # pylint: disable=too-many-positional-arguments
        """Execute ICU (In-service Cluster Upgrade) for SRX3xx chassis-cluster.

        ICU is a ~30-second disruptive upgrade with automatic failover and reboot.
        The in-service upgrade reboots both nodes in sequence with automatic failover.

        Args:
            image_name (str): Name of image.
            checksum (str): The checksum of the file.
            reboot (bool): Whether to reboot after install. Must be True for ICU. Defaults to True.
            hashing_algorithm (str): The hashing algorithm to use. Defaults to 'md5'.
            validate (bool): Perform image validation. When False, adds 'no-validate' flag. Defaults to False.
            snapshot (bool): Take post-upgrade system snapshot. Defaults to False.

        Returns:
            bool: True if upgrade completed successfully.

        Raises:
            ValueError: When reboot=False (ICU requires automatic reboot).
            OSInstallError: On upgrade failure or version verification failure.
        """
        if not reboot:
            raise ValueError("ICU (in-service cluster upgrade) requires automatic reboot; reboot=False is invalid")

        # Extract target version from image name
        match = _JUNOS_VERSION_RE.search(image_name)
        target_version = match.group(1) if match else None
        if target_version is None:
            log.warning("Host %s: Could not extract version from image %s", self.host, image_name)

        # Capture pre-upgrade uptime BEFORE initiating upgrade
        try:
            self._uptime = None
            original_uptime = self.uptime
            log.debug("Host %s: Pre-upgrade uptime: %s seconds", self.host, original_uptime)
        except Exception as uptime_exc:  # pylint: disable=broad-exception-caught
            log.warning("Host %s: Could not capture pre-upgrade uptime: %s (proceeding anyway)", self.host, uptime_exc)
            original_uptime = None

        # Issue ICU command (no-sync flag is ICU-specific)
        # Note: validate=False means we want to skip validation, so no_validate=True
        # Reactive failover: catch "primary node" RPC errors, failover, retry once
        rpc_response = None
        try:
            rpc_response = self._initiate_issu_upgrade(image_name, is_icu=True, no_validate=not validate)
        except RpcError as rpc_err:
            # Check if this is a "primary node error" by inspecting the RPC response
            err_text = str(rpc_err.rsp) if hasattr(rpc_err, "rsp") else str(rpc_err)
            if not isinstance(err_text, str):
                err_text = str(err_text)
            err_text = err_text.lower()
            if "primary node" in err_text:
                log.warning(
                    "Host %s: ICU initiation failed with 'primary node' error. Attempting failover and retry.",
                    self.host,
                )
                # Determine current node and non-primary redundancy groups
                try:
                    self.native.facts_refresh()
                    current_re = self.native.facts.get("current_re", [])
                    if not current_re or len(current_re) == 0:
                        raise DeviceNotActiveError(
                            hostname=self.hostname,
                            redundancy_state="unknown",
                            peer_redundancy_state="unknown",
                        )
                    current_node = current_re[0]

                    # Get RGs that are not primary
                    redundancy_groups = self._get_icu_redundancy_groups()
                    for rg in redundancy_groups:
                        status = self._get_node_redundancy_status(current_node, rg)
                        if status != "primary":
                            log.info("Host %s: Failing over RG %d to achieve primary", self.host, rg)
                            self._failover_redundancy_group(rg, current_node)

                    # Re-check: all RGs must be primary now
                    for rg in redundancy_groups:
                        status = self._get_node_redundancy_status(current_node, rg)
                        if status != "primary":
                            log.error(
                                "Host %s: Still not primary for RG %d after failover (status: %s)",
                                self.host,
                                rg,
                                status,
                            )
                            raise DeviceNotActiveError(
                                hostname=self.hostname,
                                redundancy_state=status,
                                peer_redundancy_state="primary" if status == "secondary" else "secondary",
                            )

                    # Retry ICU after successful failover
                    log.info("Host %s: Retrying ICU upgrade after failover", self.host)
                    rpc_response = self._initiate_issu_upgrade(image_name, is_icu=True, no_validate=not validate)
                except (CommandError, OSInstallError, DeviceNotActiveError):
                    raise
                except Exception as failover_exc:  # pylint: disable=broad-exception-caught
                    log.error("Host %s: Failover recovery failed: %s", self.host, failover_exc)
                    raise OSInstallError(hostname=self.hostname, desired_boot=image_name) from failover_exc
            else:
                # Non-primary errors are not retried
                log.error("Host %s: ICU failed with non-recoverable RPC error: %s", self.host, rpc_err)
                raise OSInstallError(hostname=self.hostname, desired_boot=image_name) from rpc_err

        if rpc_response:
            log.info("Host %s: ICU RPC response captured", self.host)
        else:
            log.info("Host %s: No RPC response (device initiated reboot)", self.host)

        # Wait for device to reboot and come back up with warm-up-then-poll pattern
        log.info("Host %s: ICU upgrade initiated. Waiting for device to reboot and synchronize", self.host)

        if original_uptime is not None:
            log.info(
                "Host %s: Waiting %s seconds before polling for reboot completion",
                self.host,
                _JUNOS_POLL_WARMUP_SECONDS,
            )
            time.sleep(_JUNOS_POLL_WARMUP_SECONDS)
            log.info("Host %s: Polling for device reboot completion", self.host)
            self._wait_for_device_reboot(original_uptime, timeout=2400, is_multiple=True)
            log.info("Host %s: Device rebooted successfully", self.host)
        else:
            log.warning("Host %s: Skipping reboot poll (uptime unavailable)", self.host)

        # Post-upgrade checks
        self._post_install_checks(
            image_name,
            is_multiple=True,
            in_service=True,
            nssu=False,
            verification_required=False,
            snapshot=snapshot,
        )

        log.info("Host %s: ICU upgrade completed successfully", self.host)
        return True

    def install_os(
        self,
        image_name,
        checksum,
        reboot=True,
        hashing_algorithm="md5",
        nssu=False,
        issu=False,
        snapshot=False,
        validate=False,
    ):  # pylint: disable=too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
        """Install OS on device and reboot.

        For multi-device setups (virtual-chassis, chassis-cluster), supports ICU/NSSU/ISSU
        upgrades and optional system snapshots after reboot. Upgrade method is auto-detected:
        - SRX300-380 chassis-cluster → ICU (in-service cluster upgrade, ~30s downtime)
        - SRX high-end chassis-cluster → ISSU (in-service software upgrade, zero downtime)
        - Virtual-chassis + nssu flag → NSSU (nonstop software upgrade)
        - Standalone or standard install → standard OS install

        In-service upgrades (ICU/ISSU/NSSU) perform rolling reboots member-by-member during
        the install, so no separate reboot is issued on those paths; completion is verified
        by polling until every member reports the target version. For ICU, the device performs
        automatic failover during reboot; the upgrade must be initiated on the primary node.

        Args:
            image_name (str): Name of image.
            checksum (str): The checksum of the file.
            reboot (bool): Whether to reboot the device after setting the boot options. Defaults to True.
                For ICU/ISSU/NSSU, must be True (automatic reboot is part of the upgrade).
            hashing_algorithm (str): The hashing algorithm to use. Valid values are md5, sha1, and sha256.
                Defaults to md5.
            nssu (bool): Enable Nonstop Software Upgrade (virtual-chassis only). Defaults to False.
            issu (bool): Ignored; ISSU and ICU are auto-detected based on device type. Defaults to False.
            snapshot (bool): Take a post-upgrade system snapshot to sync the alternate root with the
                new version. Junos does not require a snapshot to complete an upgrade, but on dual-root
                platforms an unsynced alternate slice boots the OLD version if the device ever falls back
                to it. Snapshots can take 25+ minutes per member on small-flash platforms. Defaults to False.
            validate (bool): Perform validation of the image during install. Defaults to False.
                For multi-device setups, validation can exceed 30 minutes and cause timeouts;
                validation is not recommended on multi-device platforms. When False on ICU/ISSU,
                adds no-validate flag to skip validation (faster upgrade).

        Raises:
            ValueError: When both nssu and issu are True (mutually exclusive), or when reboot=False
                is combined with an in-service (ICU/ISSU/NSSU) upgrade.
            CommandError: When ICU upgrade fails to verify primary node availability.
        """
        if nssu and issu:
            raise ValueError("nssu and issu are mutually exclusive; only one can be True")

        is_multiple = self._validate_multiple_device()
        is_chassis_cluster = self._is_chassis_cluster or self._detect_chassis_cluster()
        log.info(
            "Host %s: Multi-device detected: %s, Chassis-cluster detected: %s",
            self.host,
            is_multiple,
            is_chassis_cluster,
        )
        # TODO: test this
        if is_multiple and not validate:
            log.warning(
                "Host %s: Image validation is disabled for multi-device install; "
                "enable it only if live device testing shows no timeout issues.",
                self.host,
            )

        # ICU (in-service-upgrade) for SRX3xx chassis-cluster is a modified ISSU
        is_icu = is_chassis_cluster and self._is_srx3xx()

        # In-service upgrades only apply to multi-device setups; on a standalone
        # device the nssu/issu flags are ignored and a standard install runs.
        # ICU for SRX3xx chassis-cluster is also in-service (automatic rolling reboot).
        in_service = ((nssu or issu) and is_multiple) or is_icu
        if in_service and not reboot:
            raise ValueError(
                "reboot=False cannot be combined with in-service upgrades (NSSU/ISSU/ICU); "
                "the in-service upgrade reboots the device(s) as part of the install"
            )

        # Route to ICU path for SRX300-380 chassis-cluster (auto-detected)
        icu_complete = False
        if is_icu:
            icu_complete = self._install_os_icu(
                image_name,
                checksum,
                reboot=reboot,
                hashing_algorithm=hashing_algorithm,
                validate=validate,
                snapshot=snapshot,
            )

        if not icu_complete:
            # Standard install, NSSU, or ISSU (non-ICU) paths
            install_kwargs = {
                "package": image_name,
                "checksum": checksum,
                "checksum_algorithm": hashing_algorithm,
                "progress": True,
                "validate": validate,
                "no_copy": True,
                "timeout": 3600,
            }

            if in_service:
                install_kwargs["nssu" if nssu else "issu"] = True
                log.info(
                    "Host %s: %s enabled for multi-device upgrade",
                    self.host,
                    "NSSU" if nssu else "ISSU",
                )
            else:
                log.info("Host %s: Standard install (no NSSU/ISSU)", self.host)

            log.debug("Host %s: install_kwargs before install: %s", self.host, install_kwargs)
            # Sometimes install() returns a tuple of (ok, msg). Other times it returns a single bool
            install_ok = None
            install_msg = None
            try:
                install_ok = self.sw.install(**install_kwargs)
                log.info("Host %s: Install RPC response: %s", self.host, install_ok)
                if isinstance(install_ok, tuple):
                    install_ok, install_msg = install_ok[0], install_ok[1]
            except RpcError as rpc_err:
                log.error("Host %s: Install RPC error: %s", self.host, rpc_err)
                raise

            log.info("Host %s: install_ok result: %s", self.host, install_ok)
            if install_msg:
                log.debug("Host %s: install message: %s", self.host, install_msg)

            # In-service upgrades roll reboot per member; don't treat "A reboot is required" as outstanding.
            reboot_required = bool(install_msg) and "A reboot is required" in str(install_msg) and not in_service

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

            self._reboot_to_apply(image_name, is_multiple, in_service)

            self._post_install_checks(
                image_name,
                is_multiple,
                in_service,
                nssu,
                verification_required=not install_ok,
                snapshot=snapshot,
            )

        log.info("Host %s: OS image %s installed successfully.", self.host, image_name)
        return True

    def _reboot_to_apply(self, image_name, is_multiple, in_service):
        """Reboot to apply the installed image, unless the in-service upgrade already did.

        Args:
            image_name (str): Name of the installed image; used for log context only.
            is_multiple (bool): Whether device is in multi-device configuration.
            in_service (bool): Whether the install ran as NSSU/ISSU/ICU.

        Raises:
            CommandError: When the pre-reboot uptime cannot be determined on the
                multi-device path (the reboot is refused rather than issued blind).
        """
        if in_service:
            # In-service upgrades automatically reboot devices
            log.info(
                "Host %s: performed a in-service upgrade and reboots automatically; skipping manual reboot",
                self.host,
            )
            return

        log.info("Host %s: Rebooting device to apply OS image %s", self.host, image_name)
        if is_multiple:
            self._uptime = None
            original_uptime = self.uptime

            if original_uptime is None:
                raise CommandError(
                    command="install_os",
                    message="Could not determine pre-reboot uptime; refusing to reboot.",
                )

            self._request_system_reboot_all_members()
            self._wait_for_device_reboot(original_uptime, is_multiple=True)
        else:
            self.reboot(wait_for_reload=True)

    def _post_install_checks(
        self,
        image_name,
        is_multiple,
        in_service,
        nssu,
        verification_required=False,
        snapshot=False,
    ):  # pylint: disable=too-many-positional-arguments
        """Wait for in-service completion, optionally snapshot, and verify the running version.

        For in-service upgrades (NSSU/ISSU/ICU), waits for all members to reach the
        target version before snapshot. This completion wait already verifies every
        member runs the target version, so skips redundant verification after.
        For standard installs, post-install verification confirms the upgrade worked.

        Args:
            image_name (str): Name of the installed image; the target version is
                extracted from it. When no version can be extracted, the completion
                wait and version verification are skipped with a warning.
            is_multiple (bool): Whether device is in multi-device configuration.
            in_service (bool): Whether the install ran as NSSU/ISSU/ICU (in-service upgrade).
            nssu (bool): True for NSSU, False for ISSU; only used for log labels.
            verification_required (bool): True when the install only proceeded on the
                "A reboot is required" heuristic (PyEZ reported failure); post-reboot
                version verification is then the only proof the install worked, so an
                unverifiable image name raises instead of warning.
            snapshot (bool): Take a post-upgrade system snapshot and wait for it to
                complete. Defaults to False.

        Raises:
            OSInstallError: When ``verification_required`` is True and no version can
                be extracted from ``image_name`` to verify against.
        """
        match = _JUNOS_VERSION_RE.search(image_name)
        target_version = match.group(1) if match else None
        if target_version is None:
            if verification_required:
                log.error(
                    "Host %s: Install of %s reported failure and its result cannot be verified "
                    "(no parseable version in the image name); treating as failed.",
                    self.host,
                    image_name,
                )
                raise OSInstallError(hostname=self.hostname, desired_boot=image_name)
            log.warning(
                "Host %s: Could not extract version from image name %s; skipping post-install version checks",
                self.host,
                image_name,
            )

        verified_by_completion_wait = bool(target_version) and in_service
        if verified_by_completion_wait:
            log.info(
                "Host %s: Waiting for all members to complete %s upgrade to version %s",
                self.host,
                "NSSU" if nssu else "ISSU",
                target_version,
            )
            self._wait_for_nssu_completion(target_version, expected_members=self._vc_member_count() or None)

        # Optionally sync the alternate root with the new version after reboot/upgrade
        if snapshot:
            self.request_system_snapshot(parameters="slice alternate all-members" if is_multiple else "slice alternate")

        # Verify the install was successful by checking the running version
        if target_version and not verified_by_completion_wait:
            self._verify_install_version(target_version, is_multiple)

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

    def _remote_file_copy_shell_fetch(self, src, source_url, dest):
        r"""Download ``source_url`` straight to ``dest`` with the shell ``fetch`` binary.

        The ``file copy`` RPC stages remote fetches under the calling user's
        home directory (``/var/home/<user>`` on the ``/var`` partition) and
        only moves the file to the destination afterwards, so it fails with
        "filesystem is full" whenever the image is larger than the free space
        on ``/var`` — even when the destination filesystem has plenty of room.
        ``fetch -o`` writes directly to the destination path with no staging
        copy. ``-q`` is required, not cosmetic: fetch's progress lines
        (``89% of 119 MB``) can match PyEZ's shell-prompt pattern
        ``(%|#|$)\s`` and would end the prompt wait mid-transfer.

        Returns:
            bool: True when the file was downloaded; False when the platform
                has no ``fetch`` binary (e.g., Junos Evolved) and the caller
                should fall back to the ``file copy`` RPC.

        Raises:
            FileTransferError: When ``fetch`` ran and failed, or the shell
                session itself could not be established.
        """
        fetch_cmd = f"fetch -q -o {shlex.quote(dest)} {shlex.quote(source_url)}"
        if src.scheme == "ftp":
            fetch_cmd = f"setenv FTP_PASSIVE_MODE {'yes' if src.ftp_passive else 'no'}; {fetch_cmd}"

        exit_ok, output = False, ""
        try:
            with StartShell(self.native) as shell:
                exit_ok, output = shell.run(fetch_cmd, timeout=src.timeout)
                if not exit_ok:
                    # csh reports "fetch: Command not found."; sh reports "fetch: not
                    # found". A bare "not found" check would also match fetch's own
                    # HTTP 404 error text and misroute a real transfer failure.
                    if "command not found" in output.lower() or "fetch: not found" in output.lower():
                        log.warning(
                            "Host %s: no fetch binary on this platform; falling back to the file-copy RPC.",
                            self.host,
                        )
                        return False
                    # Remove the partial file so it does not consume the space a retry needs.
                    shell.run(f"rm -f {shlex.quote(dest)}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error("Host %s: shell fetch from %s failed: %s", self.host, src.clean_url, exc)
            raise FileTransferError(message=f"Unable to copy file from remote url {src.clean_url}: {exc}") from exc

        if not exit_ok:
            # The echoed fetch command carries the URL credential; mask it.
            error = output.replace(src.token, "*****").strip() if src.token else output.strip()
            log.error("Host %s: shell fetch from %s failed: %s", self.host, src.clean_url, error)
            raise FileTransferError(message=f"Unable to copy file from remote url {src.clean_url}: {error}")
        return True

    def _remote_file_copy_rpc(self, src, source_url, dest):
        """Copy ``source_url`` to ``dest`` with the ``file copy`` RPC.

        Issued directly rather than through PyEZ ``fs.cp``, which wraps the RPC
        in a bare ``except`` and returns False — discarding the device's actual
        error message. A successful reply may be the bool True (empty rpc-reply)
        or an XML element; only an exception means failure.
        """
        try:
            self.native.rpc.file_copy(source=source_url, destination=dest, dev_timeout=src.timeout)
        except RpcError as exc:
            log.error("Host %s: file copy from %s failed: %s", self.host, src.clean_url, exc)
            raise FileTransferError(message=f"Unable to copy file from remote url {src.clean_url}: {exc}") from exc

    def remote_file_copy(self, src: FileCopyModel = None, dest=None, file_system: str | None = None, **kwargs):
        """Copy a file to a remote device.

        For ``ftp``/``http``/``https`` URLs the transfer runs as a shell
        ``fetch`` writing directly to ``dest``, avoiding the ``file copy``
        RPC's staging copy in the user's home directory on ``/var`` (which
        fails on small-flash platforms). Other schemes, and platforms without
        a ``fetch`` binary, use the ``file copy`` RPC.

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

        # The download URL requires the filename; append ``src.file_name``
        # when the URL carries no path so callers can point at a bare host.
        source_url = src.download_url
        if not urlparse(source_url).path.strip("/"):
            source_url = f"{source_url.rstrip('/')}/{src.file_name}"

        # The ``file copy`` RPC stages remote fetches in the calling user's home
        # directory (on the small ``/var`` partition) before moving them to the
        # destination, so it fails with "filesystem is full" on small-flash
        # platforms even when the destination filesystem has room. Prefer a
        # shell ``fetch`` which writes straight to ``dest``; fall back to the
        # RPC for schemes ``fetch`` cannot handle or platforms without the binary.
        copied = False
        if src.scheme in _JUNOS_FETCH_SCHEMES:
            copied = self._remote_file_copy_shell_fetch(src, source_url, dest)
        if not copied:
            self._remote_file_copy_rpc(src, source_url, dest)

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
