"""Module for using a Cisco IOS-XR (eXR / 64-bit) device over SSH.

This driver targets 64-bit IOS-XR (eXR) platforms (initial target: NCS5000 /
NCS-5011) and implements the asynchronous OS upgrade workflow:

    install add -> poll for completion -> install activate -> reload -> install commit -> verify

The driver upgrades from a single **golden ISO** image. A golden ISO bundles the
base XR image together with the matching-version feature RPMs (IS-IS, OSPF, MPLS,
multicast, etc.) into one file, so it can be added and activated on its own — eXR
will not abort the activation demanding separate feature RPMs. Build a golden ISO
with Cisco's gisobuild tool (https://github.com/ios-xr/gisobuild). Installing a
bare base ISO plus separate feature RPMs is not supported by this driver.
"""

import re
import time

from netmiko import ConnectHandler
from netmiko.exceptions import AuthenticationException, ReadTimeout, SSHException

from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileSystemNotFoundError,
    FileTransferError,
    OSInstallError,
    RebootTimeoutError,
)
from pyntc.utils.models import FileCopyModel

# A freshly reloaded eXR node — or one hit by the upgrade workflow's rapid, short-lived
# sessions — refuses new SSH connections once it exceeds its `ssh server rate-limit`,
# closing the socket before the version exchange (the client sees "Error reading SSH
# protocol banner" or a connection timeout). These failures are transient: waiting a few
# seconds lets the per-minute rate-limit window drain, so connections are retried with a
# backoff. Override per device via the `ssh_connect_attempts` / `ssh_connect_retry_delay`
# kwargs.
DEFAULT_SSH_CONNECT_ATTEMPTS = 5
DEFAULT_SSH_CONNECT_RETRY_DELAY = 15

# Parse the running version from "show version", e.g. "Version 7.11.2".
RE_XR_VERSION = re.compile(r"Version\s+(\d+\.\d+\.\d+\w*)")


@fix_docs
class IOSXRDevice(BaseDevice):
    """Cisco IOS-XR (eXR / 64-bit) Device Implementation."""

    vendor = "cisco"

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(
        self,
        host,
        username,
        password,
        secret="",
        port=None,
        read_timeout_override=None,
        ssh_connect_attempts=DEFAULT_SSH_CONNECT_ATTEMPTS,
        ssh_connect_retry_delay=DEFAULT_SSH_CONNECT_RETRY_DELAY,
        **kwargs,
    ):  # noqa: D403  # nosec
        """PyNTC Device implementation for Cisco IOS-XR (eXR).

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            secret (str, optional): The password to escalate privilege on the device.
            port (int, optional): The port to use to establish the connection. Defaults to 22.
            read_timeout_override (int, optional): If supplied, overrides all timeouts for netmiko send_command calls.
            ssh_connect_attempts (int, optional): Number of times to try to connect to the device before giving up. Defaults to 5.
            ssh_connect_retry_delay (int, optional): Number of seconds to wait between retries when ssh_connect_attempts is >1. Defaults to 15.
            kwargs (dict): Additional arguments to pass to the Netmiko ConnectHandler.
        """
        super().__init__(host, username, password, device_type="cisco_iosxr_ssh")

        self.native = None
        self.secret = secret
        self.port = int(port) if port else 22
        self.read_timeout_override = read_timeout_override
        self._connect_attempts = ssh_connect_attempts
        self._connect_retry_delay = ssh_connect_retry_delay
        self._connected = False
        self.open()
        log.init(host=host)

    def _send_command(self, command, expect_string=None, **kwargs):
        command_args = {"command_string": command}
        if expect_string is not None:
            command_args["expect_string"] = expect_string
        command_args.update(kwargs)

        response = self.native.send_command(**command_args)

        if re.search(r"^\s*%", response, flags=re.MULTILINE) or "Error:" in response:
            log.error("Host %s: Error in %s with response: %s", self.host, command, response)
            raise CommandError(command, response)

        log.info("Host %s: Command %s was executed successfully.", self.host, command)
        return response

    def _get_file_system(self):
        """Determine the default file system or directory for device.

        Returns:
            (str): The name of the default file system or directory for the device.

        Raises:
            FileSystemNotFound: When the module is unable to determine the default file system.
        """
        raw_data = self.show("show filesystem location all")

        try:
            found_filesystems = set()
            fs_list = raw_data.split("File Systems:")[1].strip().split("\n")[1:]
            for fs in fs_list:
                size_bytes, free_bytes, fs_type, fs_flags, fs_name = fs.split()
                if "disk" in fs_type:
                    found_filesystems.add(fs_name)
                    log.debug("Host %s: Found filesystem %s.", self.host, fs_name)

            # Prefer harddisk: then disk0:
            # TODO: Do we need to support more than these?
            for fs in ["harddisk:", "disk0:"]:
                if fs in found_filesystems:
                    return fs
        except (AttributeError, IndexError, ValueError):
            pass

        log.error("host %s: Unable to determine the device's default filesystem.")
        raise FileSystemNotFoundError(hostname=self.hostname, command="show filesystem location all")

    def _uptime_components(self, uptime_full_string):
        match_weeks = re.search(r"(\d+) weeks?", uptime_full_string)
        match_days = re.search(r"(\d+) days?", uptime_full_string)
        match_hours = re.search(r"(\d+) hours?", uptime_full_string)
        match_minutes = re.search(r"(\d+) minutes?", uptime_full_string)

        weeks = int(match_weeks.group(1)) if match_weeks else 0
        days = int(match_days.group(1)) if match_days else 0
        hours = int(match_hours.group(1)) if match_hours else 0
        minutes = int(match_minutes.group(1)) if match_minutes else 0

        return weeks, days, hours, minutes

    def _uptime_to_seconds(self, uptime_full_string):
        weeks, days, hours, minutes = self._uptime_components(uptime_full_string)
        seconds = weeks * 7 * 24 * 60 * 60
        seconds += days * 24 * 60 * 60
        seconds += hours * 60 * 60
        seconds += minutes * 60
        return seconds

    def _uptime_to_string(self, uptime_full_string):
        weeks, days, hours, minutes = self._uptime_components(uptime_full_string)
        days = days + weeks * 7
        return f"{days:02d}:{hours:02d}:{minutes:02d}:00"

    def _install_add(self, source, image_name):
        """Stage the golden ISO into the install repository.

        ``install add`` returns immediately and continues asynchronously in the
        background, printing an operation id that subsequent steps reference.

        Args:
            source (str): The on-device source path, e.g. ``harddisk:/``.
            image_name (str): The golden ISO filename to add.

        Returns:
            (int): The install operation id parsed from the device response.

        Raises:
            OSInstallError: When the device response does not contain an operation id.
        """
        command = f"install add source {source} {image_name}"
        response = self.native.send_command(command, read_timeout=120)

        # Parse the operation id from the response, e.g. "Install operation 17 started".
        match = re.search(r"[Ii]nstall operation (\d+)", response)
        if match is None:
            log.error("Host %s: Unable to parse install operation id from response: %s", self.host, response)
            raise OSInstallError(hostname=self.host, desired_boot=image_name)

        operation_id = int(match.group(1))
        log.info("Host %s: install add started operation %s.", self.host, operation_id)
        return operation_id

    def _wait_for_install_operation(self, operation_id, timeout=3600, interval=30):
        """Poll ``show install log <id>`` until the operation reaches a terminal state.

        Args:
            operation_id (int): The install operation id to track.
            timeout (int): Maximum seconds to wait for a terminal state. Defaults to 3600.
            interval (int): Seconds to wait between polls. Defaults to 30.

        Raises:
            OSInstallError: When the operation aborts/fails or the timeout is exceeded.
        """
        success = re.compile(
            rf"operation\s+{operation_id}\b.*(completed successfully|succeeded)", re.IGNORECASE | re.DOTALL
        )
        failure = re.compile(rf"operation\s+{operation_id}\b.*(aborted|failed)", re.IGNORECASE | re.DOTALL)

        start = time.time()
        while time.time() - start < timeout:
            output = self.native.send_command(f"show install log {operation_id}", read_timeout=120)
            if failure.search(output):
                log.error("Host %s: install operation %s aborted/failed.", self.host, operation_id)
                raise OSInstallError(hostname=self.host, desired_boot=f"operation {operation_id}")
            if success.search(output):
                log.info("Host %s: install operation %s completed successfully.", self.host, operation_id)
                return
            time.sleep(interval)

        log.error("Host %s: install operation %s timed out after %s seconds.", self.host, operation_id, timeout)
        raise OSInstallError(hostname=self.host, desired_boot=f"operation {operation_id}")

    def _install_activate(self, operation_id, poll_interval=60, timeout=3600):
        """Activate a staged install operation and track it to completion.

        The activation is issued with ``noprompt`` (so eXR does not wait on the interactive
        reload confirmation) and runs **asynchronously** so the SSH session stays free to poll
        the install status. A synchronous activate would hold the session and, when the reload
        tore the device down, trap the read on a half-open socket until ``read_timeout``.

        For an ISO upgrade the activation always ends in a reload, so "success" manifests as
        ``show install request`` reporting *completed, pending reload* (or the SSH session
        dropping as the reload starts) — not a committed ``State : Success`` (the device
        reloads before that appears). This method polls ``show install request`` once per
        ``poll_interval`` — logging each poll — and returns when it sees the pending-reload
        marker or the session drops, and raises if the operation reports an abort/error.

        Args:
            operation_id (int): The staged ``install add`` operation id to activate.
            poll_interval (int): Seconds between status polls. Defaults to 60.
            timeout (int): Maximum seconds to wait for the activation to finish. Defaults to 3600.

        Raises:
            OSInstallError: When the activation operation aborts/fails or does not finish in time.
        """
        command = f"install activate id {operation_id} noprompt"
        log.info("Host %s: issuing activation: %s", self.host, command)
        try:
            self.native.send_command_timing(command, read_timeout=180)
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            log.info("Host %s: activation issue dropped the session (reload already underway): %s", self.host, exc)
            return

        start = time.time()
        while time.time() - start < timeout:
            time.sleep(poll_interval)
            try:
                request = self.native.send_command("show install request", read_timeout=120)
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                log.info("Host %s: session dropped while polling activation (reload underway): %s", self.host, exc)
                return
            log.info("Host %s: polled activation status.", self.host)
            if re.search(r"abort|Error[:!]", request, re.IGNORECASE):
                log.error("Host %s: activation of operation %s failed: %s", self.host, operation_id, request)
                raise OSInstallError(hostname=self.host, desired_boot=f"operation {operation_id}")
            if re.search(
                r"completed, pending reload|finished successfully|completed successfully", request, re.IGNORECASE
            ):
                log.info("Host %s: activation completed; reload imminent.", self.host)
                return

        log.error("Host %s: activation of operation %s did not finish within %ss.", self.host, operation_id, timeout)
        raise OSInstallError(hostname=self.host, desired_boot=f"operation {operation_id}")

    def _install_commit(self, retries=3, retry_delay=30, read_timeout=120):
        """Persist the activated software so it survives future reloads.

        Issued immediately after the activation reload, where the install manager can be slow
        to respond, so the command uses a generous ``read_timeout`` and is retried a few times
        on failure. Re-issuing ``install commit`` when there is nothing left to commit is a
        harmless no-op, so retrying is safe even if a prior attempt actually committed but the
        prompt was slow to return.

        Args:
            retries (int): Number of attempts before giving up. Defaults to 3.
            retry_delay (int): Seconds to wait between attempts. Defaults to 30.
            read_timeout (int): Per-attempt Netmiko read timeout. Defaults to 120.

        Raises:
            OSInstallError: When the commit does not complete cleanly after ``retries`` attempts.
        """
        for attempt in range(1, retries + 1):
            try:
                self.native.send_command("install commit", read_timeout=read_timeout)
                log.info("Host %s: install commit issued.", self.host)
                return
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                log.warning(
                    "Host %s: install commit attempt %s/%s did not return cleanly (%s).",
                    self.host,
                    attempt,
                    retries,
                    exc,
                )
                if attempt < retries:
                    time.sleep(retry_delay)
                    try:
                        self.open()
                    except Exception as open_exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                        log.debug("Host %s: reopen before commit retry failed (%s).", self.host, open_exc)

        log.error("Host %s: install commit did not complete after %s attempts.", self.host, retries)
        raise OSInstallError(hostname=self.host, desired_boot="install commit")

    def _wait_for_device_reboot(self, timeout=3600, interval=60):
        """Wait for the activation reload: watch the session drop, then poll until it returns.

        After a successful activation the device reloads. This probes the device once per
        ``interval`` — logging each poll — and requires a *drop-then-recover* transition: it
        first waits for the session to drop (reload in progress), then keeps polling on fresh
        connections until one succeeds. Requiring the drop avoids mistaking the brief still-up
        window before the reload for a completed reboot, and using fresh short-lived
        connections avoids the half-open-socket hang a long-lived read would hit.

        Args:
            timeout (int): Maximum seconds to wait for the device to return. Defaults to 3600.
            interval (int): Seconds between probes. Defaults to 60.

        Raises:
            RebootTimeoutError: When the device does not return within ``timeout``.
        """
        # Drop any existing session so each probe is a fresh connection.
        try:
            self.close()
        except Exception as close_exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            log.debug("Host %s: pre-reboot disconnect raised %s (ignored).", self.host, close_exc)
        self.native = None
        self._connected = False

        start = time.time()
        seen_down = False
        while time.time() - start < timeout:
            try:
                # This loop is itself the retry mechanism, so each probe fails fast
                # (retry=False) rather than paying the connect backoff on every poll.
                self.open(retry=False)
                self.show("show version")
                if seen_down:
                    log.info("Host %s: device is back up after reload.", self.host)
                    return
                log.info("Host %s: device still reachable; waiting for the reload to drop the session...", self.host)
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                self.native = None
                self._connected = False
                if not seen_down:
                    log.info("Host %s: device disconnected; reload in progress (%s).", self.host, exc)
                    seen_down = True
                else:
                    log.info("Host %s: device still down (%s); polling again in %ss.", self.host, exc, interval)
            time.sleep(interval)

        log.error("Host %s: device did not return within %ss while rebooting.", self.host, timeout)
        raise RebootTimeoutError(hostname=self.host, wait_time=timeout)

    @property
    def boot_options(self):
        """Get the current boot image and version from ``show install active``.

        Returns:
            (dict): ``{"sys": <active boot package>, "version": <version>}``;
                both values are ``None`` when the output cannot be parsed.
        """
        show_install_active = self.show("show install active")

        # Parse the active boot package and its version, e.g. "ncs5k-xr-7.11.2".
        match = re.search(r"(?P<sys>\S*xr-(?P<version>\d+\.\d+\.\d+\w*))", show_install_active)

        # The regex's named groups are exactly "sys" and "version".
        boot_options = match.groupdict() if match else {"sys": None, "version": None}

        log.debug("Host %s: boot options %s.", self.host, boot_options)
        return boot_options

    def close(self):
        """Disconnect from the device."""
        if self.connected:
            self.native.disconnect()
            self._connected = False
            log.debug("Host %s: Connection closed.", self.host)

    @property
    def connected(self):  # noqa: D401
        """Get the connection status of the device.

        Returns:
            (bool): True if the device is connected, else False.
        """
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value

    def enable(self):
        """No-op for IOS-XR.

        IOS-XR EXEC mode is already privileged, so there is no enable step
        analogous to IOS. Provided for API compatibility.
        """
        log.debug("Host %s: enable() is a no-op on IOS-XR.", self.host)

    def check_file_exists(self, filename, file_system=None):
        """Check whether a file exists on the device filesystem.

        Args:
            filename (str): The filename to look for.
            file_system (str, optional): Filesystem to inspect. Automatically retrieves the default filesystem if not provided.

        Returns:
            (bool): True if the file is present, False otherwise.
        """
        if file_system is None:
            file_system = self._get_file_system()

        result = self.native.send_command(f"dir {file_system}/{filename}", read_timeout=30)
        if re.search(r"No such file|No files matched|not found|Path does not exist|Error", result, re.IGNORECASE):
            log.debug("Host %s: File %s does not exist on %s.", self.host, filename, file_system)
            return False
        if re.search(re.escape(filename), result):
            log.debug("Host %s: File %s exists on %s.", self.host, filename, file_system)
            return True

        log.debug("Host %s: File %s not found in 'dir' output on %s.", self.host, filename, file_system)
        return False

    def remote_file_copy(self, src: FileCopyModel, dest=None, file_system=None, **kwargs):
        """Copy a file from a remote URL onto the device filesystem.

        Pulls the file specified by ``src`` from a remote server (FTP/TFTP/SCP/HTTP/HTTPS)
        using the IOS-XR ``copy`` command and saves it to ``file_system``. The transfer is
        verified by confirming the file exists after copy. **Checksum verification is not performed**
        on IOS-XR in this release; the ``checksum`` on ``src`` is not validated.

        Args:
            src (FileCopyModel): The source specification (URL, credentials, timeout).
            dest (str, optional): Destination filename. Defaults to ``src.file_name``.
            file_system (str, optional): Target filesystem. Automatically retrieves the default filesystem if not provided.
            kwargs (dict): Additional keyword arguments (unused).

        Raises:
            TypeError: When ``src`` is not a ``FileCopyModel``.
            FileTransferError: When the transfer fails or the file is absent afterward.
        """
        if not isinstance(src, FileCopyModel):
            raise TypeError("src must be an instance of FileCopyModel")

        if file_system is None:
            file_system = self._get_file_system()
        if dest is None:
            dest = src.file_name

        if self.check_file_exists(dest, file_system=file_system):
            log.info("Host %s: File %s already present on %s; skipping copy.", self.host, dest, file_system)
            return

        self._pre_transfer_space_check(src, file_system)
        current_prompt = self.native.find_prompt()

        # Prompts IOS-XR may emit during an interactive copy.
        prompt_answers = {
            r"Destination filename": "",
            r"Host name or IP address": "",
            r"Source username|Username": src.username or "",
            r"Password": src.token or "",
            r"yes/no|\[confirm\]|Are you sure": "",
        }
        keys = list(prompt_answers.keys()) + [re.escape(current_prompt)]
        expect_regex = f"({'|'.join(keys)})"

        command = f"copy {src.clean_url} {file_system}/{dest}"
        if src.vrf and src.scheme not in {"http", "https"}:
            command = f"{command} vrf {src.vrf}"

        # Bypass _send_command: a copy may emit benign "%" lines that are not failures.
        output = self.native.send_command(command, expect_string=expect_regex, read_timeout=src.timeout)

        # Walk any interactive prompts. Netmiko strips the trailing prompt from the output,
        # so the post-copy existence check (below) is the authoritative success signal; this
        # loop only answers prompts and surfaces explicit error markers early.
        for _ in range(10):
            if re.search(
                r"Successfully copied|Copy operation success|bytes copied|copied in|\[OK\]|Download Complete|transfer successful",
                output,
                flags=re.IGNORECASE,
            ):
                log.info("Host %s: File %s transfer reported success.", self.host, dest)
                break
            if re.search(
                r"%Error|Error opening|Invalid input|Failed|Aborted|denied|No such file|Connection refused|timed out|could not",
                output,
                flags=re.IGNORECASE,
            ):
                log.error("Host %s: File transfer error for %s: %s", self.host, dest, output)
                raise FileTransferError
            for prompt, answer in prompt_answers.items():
                if re.search(prompt, output, re.IGNORECASE):
                    is_password = prompt == r"Password"
                    output = self.native.send_command(
                        answer, expect_string=expect_regex, read_timeout=src.timeout, cmd_verify=not is_password
                    )
                    break
            else:
                # No recognised prompt and no explicit marker; defer to the existence check.
                break

        if not self.check_file_exists(dest, file_system=file_system):
            log.error("Host %s: File %s not found after transfer.", self.host, dest)
            raise FileTransferError

        log.info("Host %s: File %s copied to %s and verified present.", self.host, dest, file_system)

    @property
    def hostname(self):
        """Get the hostname of the device.

        Returns:
            (str): The device hostname derived from the CLI prompt.
        """
        if self._hostname is None:
            prompt = self.native.find_prompt()
            self._hostname = re.sub(r"^RP/\S+/CPU\d+:", "", prompt).strip().rstrip("#>")
        return self._hostname

    def _image_booted(self, image_name, image_pattern=r"(\d+\.\d+\.\d+\w*)", **vendor_specifics):
        image_match = re.search(image_pattern, image_name)
        if image_match is None:
            log.info("Host %s: Unable to parse a version from image %s.", self.host, image_name)
            return False
        image_version = image_match.group(1)

        booted_version = self.boot_options.get("version")
        if booted_version is None:
            version_data = self.show("show version")
            version_match = RE_XR_VERSION.search(version_data)
            booted_version = version_match.group(1) if version_match else None

        booted = booted_version == image_version
        if booted:
            log.info("Host %s: Image %s booted successfully.", self.host, image_name)
        else:
            log.info("Host %s: Image %s not booted (running %s).", self.host, image_name, booted_version)
        return booted

    @property
    def install_mode(self):
        """Indicate whether the device is operating in install mode.

        eXR is always install-mode (there is no legacy boot-from-image state),
        so this always returns ``True``. Provided for ``BaseDevice`` parity.

        Returns:
            (bool): Always ``True``.
        """
        return True

    def _get_free_space(self, file_system=None):
        """Return free bytes on ``file_system`` as reported by ``dir`` output.

        Args:
            file_system (str, optional): Target filesystem. Automatically retrieves the default filesystem if not provided.

        Returns:
            (int): Free bytes available on ``file_system``.

        Raises:
            CommandError: When the free space cannot be parsed from ``dir`` output.
        """
        if file_system is None:
            file_system = self._get_file_system()

        raw_data = self.show(f"dir {file_system}")
        # eXR reports the trailer in kbytes (e.g. "9948012 kbytes total (9396256 kbytes free)");
        # other contexts may use plain bytes. Capture the unit and normalise to bytes.
        match = re.search(r"\((\d+)\s+(k|m|g)?bytes\s+free", raw_data, re.IGNORECASE)
        if match is None:
            log.error("Host %s: could not parse free space from 'dir %s'.", self.host, file_system)
            raise CommandError(command=f"dir {file_system}", message="Unable to parse free space from dir output.")

        multipliers = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
        unit = (match.group(2) or "").lower()
        free_bytes = int(match.group(1)) * multipliers[unit]
        log.debug("Host %s: %s bytes free on %s.", self.host, free_bytes, file_system)
        return free_bytes

    def install_os(self, image_name, reboot=True, **vendor_specifics):
        """Install a golden IOS-XR ISO and verify the device boots into it.

        Orchestrates the eXR install workflow over the native primitives:
        ``install add`` (golden ISO) -> poll for completion -> ``install activate`` ->
        poll the activation operation -> wait for reboot -> ``install commit`` -> verify.

        ``image_name`` must be a **golden ISO** that already bundles the base XR image
        and the matching-version feature RPMs (IS-IS, OSPF, MPLS, multicast, etc.). A
        bare base ISO cannot be activated on its own when feature packages are active —
        eXR aborts the activation demanding the matching RPMs — so build a golden ISO
        with Cisco's gisobuild tool (https://github.com/ios-xr/gisobuild) and stage that
        single file. Installing a base ISO plus separate feature RPMs is not supported.

        Args:
            image_name (str): The golden ISO filename already staged on the device.
            reboot (bool): Must be ``True``; activation reloads the device automatically.
            vendor_specifics (dict, optional): Supports ``timeout`` (default 3600) for the
                install-operation and reboot waits.

        Returns:
            (bool): True if the install ran and succeeded, False if the device was
                already running ``image_name``.

        Raises:
            ValueError: When ``reboot`` is False (eXR always reloads during activation).
            OSInstallError: When activation aborts or the device does not boot into
                ``image_name`` after install.
        """
        timeout = vendor_specifics.get("timeout", 3600)

        if self._image_booted(image_name):
            log.info("Host %s: OS image %s already booted; nothing to install.", self.host, image_name)
            return False

        if not reboot:
            raise ValueError(
                "IOS-XR devices reload automatically during 'install activate'; "
                "the reboot argument cannot be set to False."
            )

        add_id = self._install_add(f"{self._get_file_system()}/", image_name)
        self._wait_for_install_operation(add_id, timeout=timeout)
        self._install_activate(add_id, timeout=timeout)
        self._wait_for_device_reboot(timeout=timeout)
        self._install_commit()

        if not self._image_booted(image_name):
            log.error("Host %s: OS install error for image %s.", self.host, image_name)
            raise OSInstallError(hostname=self.host, desired_boot=image_name)

        log.info("Host %s: OS image %s installed successfully.", self.host, image_name)
        return True

    def _connect(self, attempts):
        """Establish a Netmiko connection, retrying transient SSH failures with backoff.

        eXR refuses new SSH sessions once its ``ssh server rate-limit`` is exceeded — and
        the upgrade workflow opens many short-lived sessions in quick succession, so a fresh
        connection (e.g. the post-reboot verification) can be rejected: the device closes the
        socket before the version exchange, surfacing as ``Error reading SSH protocol banner``
        or a connection timeout. These are transient, so connect is retried with a backoff
        long enough to let the per-minute window drain. Authentication failures are not
        transient and are re-raised immediately.

        Args:
            attempts (int): Maximum number of connection attempts.

        Returns:
            ConnectHandler: A live Netmiko connection.

        Raises:
            AuthenticationException: On a genuine auth failure (never retried).
            SSHException: When every attempt fails to connect (last error re-raised).
        """
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return ConnectHandler(
                    device_type="cisco_xr",
                    ip=self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    read_timeout_override=self.read_timeout_override,
                    secret=self.secret,
                    # Keepalives let the status polls notice a dropped session promptly.
                    keepalive=30,
                    verbose=False,
                )
            except AuthenticationException:
                # Bad credentials are not transient — fail fast.
                raise
            except (SSHException, OSError, EOFError) as exc:
                # SSHException covers Netmiko's banner/timeout wrappers and raw paramiko
                # banner errors; OSError/EOFError cover the rate-limited socket close.
                last_exc = exc
                if attempt < attempts:
                    log.info(
                        "Host %s: SSH connect attempt %s/%s failed (%s); retrying in %ss.",
                        self.host,
                        attempt,
                        attempts,
                        exc,
                        self._connect_retry_delay,
                    )
                    time.sleep(self._connect_retry_delay)
        log.error("Host %s: SSH connect failed after %s attempts.", self.host, attempts)
        raise last_exc

    def open(self, retry=True):
        """Open a connection to the network device.

        Args:
            retry (bool): Retry transient SSH failures (rate-limit / banner) with backoff.
                Defaults to True. Callers that run their own polling loop (e.g.
                ``_wait_for_device_reboot``) pass False so each probe fails fast.
        """
        if self.connected:
            try:
                self.native.find_prompt()
            except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                self._connected = False

        if not self.connected:
            self.native = self._connect(self._connect_attempts if retry else 1)
            self._connected = True

        log.debug("Host %s: Connection to controller was opened successfully.", self.host)

    @property
    def os_version(self):
        """Get the running OS version from ``show version``.

        Returns:
            (str): The version string (e.g. ``7.11.2``), or ``None`` if unparsable.
        """
        if self._os_version is None:
            version_data = self.show("show version")
            match = RE_XR_VERSION.search(version_data)
            self._os_version = match.group(1) if match else None

        log.debug("Host %s: OS version %s.", self.host, self._os_version)
        return self._os_version

    def reboot(self, wait_for_reload=False, **kwargs):
        """Reboot the device.

        Args:
            wait_for_reload (bool): Whether to also run ``_wait_for_device_reboot``. Defaults to False.
            kwargs (dict): Additional arguments to pass to Netmiko.
        """
        if kwargs.get("confirm"):
            log.warning("Passing 'confirm' to reboot method is deprecated.")

        try:
            self.native.send_command_timing("reload")
            # IOS-XR prompts "Proceed with reload?" — confirm with a newline.
            try:
                self.native.send_command_timing("\n", read_timeout=10)
            except ReadTimeout as expected_exception:
                log.info("Host %s: Device rebooted.", self.host)
                log.info("Hit expected exception during reload: %s", expected_exception.__class__)
            if wait_for_reload:
                time.sleep(10)
                self._wait_for_device_reboot()
        except Exception as err:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            log.error(err)
            log.error(err.__class__)

    def set_boot_options(self, image_name, **vendor_specifics):
        """Not supported on IOS-XR.

        eXR has no separate set-boot step: boot selection is performed atomically
        by ``install_os`` via ``install activate`` + ``install commit``.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "IOS-XR has no separate set-boot step; boot selection is performed by install_os "
            "via 'install activate' + 'install commit'."
        )

    def config(self, command, **netmiko_args):
        """Not implemented for IOS-XR.

        Configuration management is out of scope for this OS-upgrade driver in the current
        release; only the upgrade workflow is supported.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("config() is not implemented for the IOS-XR driver in this release.")

    def save(self, filename=None):
        """Not supported on IOS-XR.

        eXR software state is committed atomically by ``install_os`` (via ``install commit``);
        there is no standalone save step.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "IOS-XR has no standalone save; software is committed by install_os via 'install commit'."
        )

    def show(self, command, expect_string=None, **netmiko_args):
        """Run a command on the device.

        IOS-XR EXEC mode is already privileged, so no enable step is performed.

        Args:
            command (str|list): Command(s) to run.
            expect_string (str, optional): Expected prompt string. Defaults to None.
            netmiko_args (dict): Additional arguments passed to Netmiko's send_command.

        Returns:
            (str|list): Command output; a list when ``command`` is a list.

        Raises:
            CommandListError: When ``command`` is a list and one of the commands fails.
        """
        if isinstance(command, list):
            responses = []
            entered_commands = []
            for command_instance in command:
                entered_commands.append(command_instance)
                try:
                    responses.append(self._send_command(command_instance))
                except CommandError as e:
                    raise CommandListError(entered_commands, command_instance, e.cli_error_msg)
            return responses
        return self._send_command(command, expect_string=expect_string, **netmiko_args)

    @property
    def uptime(self):
        """Get uptime from the device.

        Returns:
            (int): Uptime in seconds.
        """
        if self._uptime is None:
            version_data = self.show("show version")
            match = re.search(r"uptime is (.+)", version_data)
            uptime_full_string = match.group(1) if match else ""
            self._uptime = self._uptime_to_seconds(uptime_full_string)

        log.debug("Host %s: Uptime %s.", self.host, self._uptime)
        return self._uptime

    @property
    def uptime_string(self):
        """Get uptime in ``dd:hh:mm:ss`` format.

        Returns:
            (str): Uptime of the device.
        """
        if self._uptime_string is None:
            version_data = self.show("show version")
            match = re.search(r"uptime is (.+)", version_data)
            uptime_full_string = match.group(1) if match else ""
            self._uptime_string = self._uptime_to_string(uptime_full_string)

        return self._uptime_string
