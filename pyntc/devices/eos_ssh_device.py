"""Module for using an Arista EOS device over SSH.

This driver exists for environments where eAPI (``management api http-commands``) is not
available. It exposes the same public API as
:class:`~pyntc.devices.eos_device.EOSDevice`; only the transport differs.

Structured output is obtained with the CLI's ``| json`` pipe, which renders the same
document eAPI returns -- the pipe is a pure CLI feature and does **not** require eAPI to be
enabled. Because the key names match, every fact property, the boot-option handling and the
whole file-transfer family are inherited from ``EOSDevice`` unchanged.
"""

import json
import os
import re
import time

from netmiko import ConnectHandler

from pyntc import log
from pyntc.devices.base_device import BaseDevice, fix_docs
from pyntc.devices.eos_device import DEFAULT_REBOOT_TIMEOUT, EOSDevice
from pyntc.errors import (
    CommandError,
    CommandListError,
    FileTransferError,
    MaintModeProfileError,
    OSInstallError,
    RebootTimeoutError,
    SocketClosedError,
)

DEFAULT_SSH_PORT = 22

# Only "show" commands may be piped to "| json". EOSDevice routes five EXEC/config commands
# through show(raw_text=False) whose return value it discards -- "copy running-config ...",
# "reload now", "configure replace ... force" and "install source ..." -- and
# "reload now | json" is not a valid command.
RE_JSON_ELIGIBLE = re.compile(r"^\s*show\b")

# EOS reports CLI failures with a leading "% " token. "Invalid input" also appears for
# commands that have no JSON renderer, which _load_json turns into a CommandError rather
# than silently falling back to text parsing (a fallback would return a differently shaped
# document and produce wrong facts instead of an error).
RE_EOS_CLI_ERROR = re.compile(r"^%\s|^Invalid input|^Error:", re.MULTILINE)

# Commands whose default Netmiko read timeout (100s) is too short. Resolving the timeout
# from the command text -- rather than adding a **netmiko_args parameter -- keeps show()'s
# signature byte-identical to EOSDevice.show(), so inherited callers such as
# ``set_boot_options``, ``save``, ``checkpoint`` and ``rollback`` work without overrides.
COMMAND_READ_TIMEOUTS = (
    (re.compile(r"^\s*install\s+source\b"), 3600),
    (re.compile(r"^\s*copy\s+running-config\b"), 300),
    (re.compile(r"^\s*configure\s+replace\b"), 300),
    (re.compile(r"^\s*show\s+(running|startup)-config\b"), 120),
)
DEFAULT_READ_TIMEOUT = 100


@fix_docs
class EOSSSHDevice(EOSDevice):
    """Arista EOS Device Implementation over SSH."""

    # pylint: disable=too-many-arguments, too-many-positional-arguments, super-init-not-called
    def __init__(self, host, username, password, secret="", port=None, **kwargs):  # nosec  # noqa: D403
        """PyNTC Device implementation for Arista EOS over SSH.

        Args:
            host (str): The address of the network device.
            username (str): The username to authenticate with the device.
            password (str): The password to authenticate with the device.
            secret (str): The password to escalate privilege on the device.
            port (int): The SSH port to connect on. Defaults to 22. Note this differs from
                ``EOSDevice.port``, which is the eAPI port.
            kwargs (dict): Additional arguments passed to Netmiko's ``ConnectHandler``.
        """
        # Deliberately skips EOSDevice.__init__, which eagerly builds a pyeapi connection
        # and takes eAPI-only arguments (transport/timeout). Going straight to BaseDevice
        # keeps the shared state without the eAPI wiring.
        BaseDevice.__init__(  # pylint: disable=non-parent-init-called
            self, host, username, password, device_type="arista_eos_ssh"
        )
        self.native = None
        self.secret = secret
        self.port = int(port) if port else DEFAULT_SSH_PORT
        self.netmiko_kwargs = kwargs
        self._connected = False
        self.open()
        log.init(host=host)

    @property
    def uptime(self):
        """Get device uptime in seconds."""
        return self.show("show version")["uptime"]

    @property
    def vlans(self):
        """Get list of VLANs on device.

        ``EOSDevice`` delegates to ``EOSVlans``, which is pyeapi-only
        (``device.native.api("vlans")``). Over SSH the same data comes from
        ``show vlan | json``, whose ``vlans`` key is a dict keyed by VLAN id.

        Returns:
            (list): List of VLAN ids as strings.
        """
        if self._vlans is None:
            # sorted() over str keys, matching EOSVlans.get_list()'s lexicographic ordering.
            self._vlans = sorted(self.show("show vlan")["vlans"].keys())

        log.debug("Host %s: Vlans %s", self.host, self._vlans)
        return self._vlans

    @property
    def native_ssh(self):
        """Alias for ``native`` so inherited Netmiko-backed code works unchanged.

        ``EOSDevice`` reaches for ``self.native_ssh`` in ``enable``, ``file_copy``,
        ``check_file_exists``, ``get_remote_checksum`` and ``remote_file_copy``. Only
        ``EOSDevice.open`` ever assigns it, and this class overrides ``open``, so exposing
        it read-only is safe.

        Returns:
            (netmiko.BaseConnection): The active Netmiko connection.
        """
        return self.native

    @staticmethod
    def _read_timeout_for(command: str):
        """Resolve the Netmiko read timeout to use for ``command``.

        Args:
            command (str): The command about to be sent.

        Returns:
            (int): Timeout in seconds.
        """
        for pattern, timeout in COMMAND_READ_TIMEOUTS:
            if pattern.match(command):
                return timeout
        return DEFAULT_READ_TIMEOUT

    def _check_output_for_errors(self, command: str, output: str):
        """Raise ``CommandError`` when the device reported a CLI error.

        Args:
            command (str): The command that was sent.
            output (str): The device response.

        Raises:
            CommandError: When ``output`` reports an error.
        """
        if RE_EOS_CLI_ERROR.search(output):
            log.error("Host %s: Error in %s with response: %s", self.host, command, output)
            raise CommandError(command, output)

    def _load_json(self, command: str, output: str):
        """Parse ``| json`` output.

        Args:
            command (str): The command that produced ``output``.
            output (str): Raw device response.

        Returns:
            (dict): The parsed document.

        Raises:
            CommandError: When the output is not valid JSON, which on EOS means the command
                has no JSON renderer.
        """
        try:
            return json.loads(output)
        except ValueError:
            log.error("Host %s: Command %s did not return JSON: %s", self.host, command, output)
            raise CommandError(command, f"Command does not support JSON output: {output}")

    def _os_updated(self, prev_version: str) -> bool:
        """Confirm the running OS version changed.

        Args:
            prev_version (str): The previous running OS version used for
                comparison.

        Returns:
            True if the running OS version has changed, False if it has
                not.
        """
        current_version = self.show("show version")["version"]
        if current_version != prev_version:
            log.info("Host %s: Version changed from %s to %s", self.host, prev_version, current_version)
            return True

        log.error("Host %s: Still running version %s", self.host, prev_version)
        return False

    def _send_command(self, command, error_command=None, **netmiko_args):
        """Send a single command and check the response for errors.

        Args:
            command (str): The command to send on the wire.
            error_command (str, optional): The command to name in a raised ``CommandError``.
                Defaults to ``command``. ``show`` passes the caller's original command so
                errors do not leak the ``| json`` suffix, matching the plain command name
                that pyeapi reports on ``EOSDevice``.
            netmiko_args (dict): Additional arguments for Netmiko's ``send_command``.

        Returns:
            (str): The raw device response.
        """
        netmiko_args.setdefault("read_timeout", self._read_timeout_for(command))
        response = self.native.send_command(command, **netmiko_args)
        self._check_output_for_errors(error_command or command, response)
        return response

    def _wait_for_reload(self, prev_uptime: float, timeout: int) -> None:
        """Block until device successfully reloads.

        Tries to retrieve and compare the current uptime to the previous
        uptime. If the current uptime is less than the previous uptime,
        the reload is considered successful. If the current uptime is
        greater than the previous uptime or the device is unreachable
        and the timeout value has not expired, the comparison will be
        reattempted again in 15 seconds. The method fails if the reload
        doesn't succeed before the timeout value expires.

        Args:
            prev_uptime (float): The uptime value prior to device reload
                in seconds.
            timeout (int): The maximum time in seconds to wait before
                flagging the reload as a failure.

        Raises:
            RebootTimeoutError: If the reload doesn't succeed before the
                timeout value expires.
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                current_uptime = self.uptime
                if current_uptime < prev_uptime:
                    log.info(
                        "Host %s: Device reload successful (current uptime %s < previous uptime %s)",
                        self.host,
                        current_uptime,
                        prev_uptime,
                    )
                    return
            except Exception as exc:  # pylint: disable=broad-except
                log.debug("Host %s: Reload probe failed (%s); will retry", self.host, exc)
            time.sleep(15)

        log.error("Host %s: Reload timer exceeded (%ss)", self.host, timeout)
        raise RebootTimeoutError(self.hostname, timeout)

    def close(self):
        """Disconnect from the device.

        Note this differs from ``EOSDevice.close``, which is a no-op because eAPI is
        stateless. An SSH session holds a real socket that should be released.
        """
        if self._connected:
            self.native.disconnect()
            self._connected = False
            log.debug("Host %s: Connection closed.", self.host)

    def config(self, command: str | list):
        """Send configuration commands to a device.

        Args:
            command (str, list): String with single command, or list with multiple commands.

        Raises:
            CommandError: When ``commands`` is a str and the device reports an error.
            CommandListError: When ``commands`` is a list and one command reports an error.
        """
        self.open()
        self.enable()

        original_commands_is_str = isinstance(command, str)
        command_list = [command] if original_commands_is_str else list(command)

        entered_commands = []
        try:
            for cmd in command_list:
                entered_commands.append(cmd)
                # Multi-line commands (e.g. "banner motd\n...\nEOF") drop the CLI into an
                # input mode whose echo Netmiko's cmd_verify cannot match; verification must
                # be disabled for them or send_config_set raises ReadTimeout.
                output = self.native.send_config_set(cmd, exit_config_mode=False, cmd_verify="\n" not in cmd)
                try:
                    self._check_output_for_errors(cmd, output)
                except CommandError as err:
                    if original_commands_is_str:
                        raise
                    raise CommandListError(entered_commands, cmd, err.cli_error_msg) from err
        finally:
            # Never leave the session parked in config mode, even on failure.
            self.native.exit_config_mode()

        log.info("Host %s: Device configured with commands %s.", self.host, command)

    def file_copy(self, src, dest=None, file_system=None):
        """Copy a local file to the device over SCP.

        Mirrors ``IOSDevice.file_copy``: existence and integrity are established with CLI
        commands rather than Netmiko's shell-based helpers, so no ``bash`` access is needed.
        ``AristaFileTransfer.enable_scp()`` raises ``NotImplementedError``, so unlike IOS
        there is no SCP-enable step -- EOS serves SCP without one.

        Args:
            src (str): Path to the local file to send.
            dest (str, optional): Remote filename. Defaults to the basename of ``src``.
            file_system (str, optional): Target filesystem. Auto-detected when omitted.

        Raises:
            SocketClosedError: When the session drops mid-transfer and the file did not land.
            FileTransferError: When the transfer fails, or the file cannot be verified
                afterwards.
            NotEnoughFreeSpaceError: When ``file_system`` has less room than ``src`` needs.
        """
        self.open()
        self.enable()
        if file_system is None:
            file_system = self._get_file_system()

        dest = dest or os.path.basename(src)
        local_checksum = self.get_local_checksum(src)
        log.debug("Host %s: Local checksum for file %s is %s.", self.host, src, local_checksum)

        if self.verify_file(local_checksum, dest, file_system=file_system):
            log.info("Host %s: File %s already present and verified; skipping.", self.host, dest)
            return

        self._check_free_space(os.path.getsize(src), file_system=file_system)
        file_copy = self._file_copy_instance(src, dest, file_system=file_system)

        try:
            file_copy.establish_scp_conn()
            file_copy.transfer_file()
            log.info("Host %s: File %s transferred successfully.", self.host, src)
        except OSError as error:
            # A dropped control channel does not necessarily mean a failed transfer;
            # compare_md5() uses the CLI "verify" command, so it is safe without a shell.
            if not file_copy.compare_md5():
                log.error("Host %s: Socket closed error %s", self.host, error)
                raise SocketClosedError(message=error) from error
            log.error("Host %s: OS error %s", self.host, error)
        except:  # noqa: E722
            log.error("Host %s: File transfer error %s", self.host, FileTransferError.default_message)
            raise FileTransferError
        finally:
            file_copy.close_scp_chan()

        # Long transfers can outlive the control channel; make sure it is usable again.
        self.open()

        if not self.verify_file(local_checksum, dest, file_system=file_system):
            log.error(
                "Host %s: Attempted file copy, but could not validate file existed after transfer %s",
                self.host,
                FileTransferError.default_message,
            )
            raise FileTransferError

    def file_copy_remote_exists(self, src, dest=None, file_system=None):
        """Check whether ``src`` already exists on the device with a matching checksum.

        ``EOSDevice`` answers this through Netmiko's ``AristaFileTransfer``, which drops into
        the switch's Linux shell (``bash`` then ``/bin/ls``). That requires shell privileges
        the connecting account may not have. This override uses the CLI instead --
        ``dir <file_system>/<file>`` and ``verify /md5 <file_system><file>`` -- matching how
        ``IOSDevice`` already behaves.

        Args:
            src (str): Path to the local file to check for.
            dest (str, optional): Remote filename. Defaults to the basename of ``src``.
            file_system (str, optional): Target filesystem. Auto-detected when omitted.

        Returns:
            (bool): True when the remote file exists and its checksum matches ``src``.
        """
        self.open()
        self.enable()
        if file_system is None:
            file_system = self._get_file_system()

        dest = dest or os.path.basename(src)
        local_checksum = self.get_local_checksum(src)
        exists = self.verify_file(local_checksum, dest, file_system=file_system)

        log.debug("Host %s: File %s already on remote: %s.", self.host, src, exists)
        return exists

    def install_os(self, image_name: str, file_system: str | None = None, reboot=True, **vendor_specifics) -> bool:
        """Install a different OS version.

        Args:
            image_name (str): The target image filename to install.
            file_system (str | None): The device's target file system
                where the software image is stored, defaults to None.
            reboot (bool): Reloads the device when True.
            vendor_specifics (dict): Any pre-loaded vendor-specific kwargs.

        Returns:
            (bool): True when the installation is successful, False when
                the target image is already installed.

        Raises:
            OSInstallError: If the image installation fails.
        """
        if self._image_booted(image_name):
            log.info("Host %s: OS image '%s' already installed", self.host, image_name)
            return False

        file_system = file_system or self._get_file_system()
        command = f"install source {file_system}{image_name}"
        self.open()
        self.enable()
        if reboot:
            timeout = vendor_specifics.get("timeout", 900)
            command += " reload now"
            version_output = self.show("show version")
            version = version_output["version"]
            uptime = version_output["uptime"]
            self._send_command(command, read_timeout=300, expect_string=r"going down for reboot|%")
            self._wait_for_reload(uptime, timeout)
            if self._os_updated(version):
                log.info("Host %s: OS image '%s' installed successfully", self.host, image_name)
                return True
            log.error("Host %s: Failed to install OS image '%s'", self.host, image_name)
            raise OSInstallError(self.hostname, image_name)
        self._send_command(command, read_timeout=300)
        log.info("Host %s: OS image '%s' installed, reload device to finalize", self.host, image_name)
        return True

    def maintenance_mode(self, unit="System", enable=True, transition_timer=300):
        """Enter or exit maintenance mode.

        Sends config commands to transition the maintenance mode state,
        entering or exiting based on the `enable` value. Attempts to
        confirm successful transition in the alloted time based on the
        provided `transition_timer` value.

        Args:
            unit (str): The specified unit to use when entering or
                exiting maintenance mode, defaults to `System`.
            enable (bool): Enters maintenance mode when True, exits
                maintenance mode when False.
            transition_timer (int): Duration in seconds to wait for
                maintenance state to succesfully transition, defaults to
                300 seconds.

        Returns:
            (bool): True if state transition successful, else False.

        Raises:
            MaintModeProfileError: If the provided unit name does not
                already exist on the target device.
        """
        commands = [
            "maintenance",
            f"unit {unit}",
        ]
        if enable:
            commands.append("quiesce")
            desired_state = "underMaintenance"
        else:
            commands.append("no quiesce")
            desired_state = "active"

        units = self.show("show maintenance")["units"]
        if unit not in units.keys():
            raise MaintModeProfileError(self.hostname, unit)
        self.config(commands)
        start = time.time()
        while time.time() - start < transition_timer:
            actual_state = self.show("show maintenance")["units"][unit]["state"]
            if actual_state == desired_state:
                log.debug("Host %s: Maintenance state successfully transitioned to '%s'", self.host, unit)
                return True
            log.debug("Host %s: Maintenance state currently '%s', will retry", self.host, actual_state)
            time.sleep(10)

        log.error(
            "Host %s: Transition state timer (%ss) has expired, maintenance state currrently '%s'",
            self.host,
            transition_timer,
            actual_state,
        )
        return False

    def open(self):
        """Open, or re-validate, the Netmiko SSH connection to the device."""
        if self._connected:
            try:
                self.native.find_prompt()
            except Exception:  # pylint: disable=broad-except
                self._connected = False

        if not self._connected:
            self.native = ConnectHandler(
                device_type="arista_eos",
                host=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                secret=self.secret,
                verbose=False,
                **self.netmiko_kwargs,
            )
            self._connected = True

        log.debug("Host %s: Connection to device was opened successfully.", self.host)

    def reboot(self, wait_for_reload=False, timeout=DEFAULT_REBOOT_TIMEOUT, **kwargs):
        """Reload the device.

        Unlike eAPI, the SSH session dies as the reload executes, so the command is sent
        with ``send_command_timing`` and the resulting transport error is expected.

        Args:
            wait_for_reload (bool): When True, block until the device's boot time advances
                past the pre-reboot value. Defaults to False.
            timeout (int): Max seconds to poll when ``wait_for_reload`` is True.
            kwargs (dict): Additional keyword arguments, such as confirm.

        Raises:
            RebootTimeoutError: When the device does not return within ``timeout``.

        Example:
            >>> device = EOSSSHDevice(**connection_args)
            >>> device.reboot()
            >>>
        """
        if kwargs.get("confirm"):
            log.warning("Passing 'confirm' to reboot method is deprecated.")

        original_boot_time = self.boot_time if wait_for_reload else None
        try:
            self.native.send_command_timing("reload now")
        except Exception as err:  # pylint: disable=broad-except
            log.debug("Host %s: Session dropped during reload, as expected (%s).", self.host, err)

        # The socket is gone regardless of how the command returned; force the next
        # operation to reconnect rather than reuse a dead handle.
        self._connected = False
        log.info("Host %s: Device rebooted.", self.host)

        if wait_for_reload:
            # Both arguments are numeric; naming them prevents a transposition from
            # silently satisfying the "boot time advanced" check on the first poll.
            self._wait_for_device_reboot(original_boot_time=original_boot_time, timeout=timeout)

    def show(self, commands: str | list, raw_text: bool = False):
        """Send show command(s) to the device.

        Args:
            commands (str, list): String with single command, or list with multiple commands.
            raw_text (bool, optional): False to return structured data via the ``| json``
                pipe, True to return the raw CLI text. Defaults to False.

        Returns:
            (dict): When ``commands`` is a str and ``raw_text`` is False. Non-show commands
                cannot be piped to ``| json``; they run as plain text and return an empty dict.
            (str): When ``commands`` is a str and ``raw_text`` is True.
            (list): When ``commands`` is a list.

        Raises:
            CommandError: When ``commands`` is a str and the device reports an error.
            CommandListError: When ``commands`` is a list and one command reports an error.
        """
        self.open()
        self.enable()

        original_commands_is_str = isinstance(commands, str)
        command_list = [commands] if original_commands_is_str else list(commands)

        responses = []
        entered_commands = []
        for command in command_list:
            entered_commands.append(command)
            as_json = not raw_text and bool(RE_JSON_ELIGIBLE.match(command))
            cli_command = f"{command} | json" if as_json else command
            try:
                output = self._send_command(cli_command, error_command=command)
                if as_json:
                    output = self._load_json(command, output)
            except CommandError as err:
                if original_commands_is_str:
                    raise
                raise CommandListError(entered_commands, command, err.cli_error_msg) from err

            if raw_text or as_json:
                responses.append(output)
            else:
                # Non-show command sent with raw_text=False (checkpoint, save, rollback,
                # reboot, set_boot_options). Every inherited caller discards the result,
                # so an empty dict preserves EOSDevice's contract.
                responses.append({})

        if original_commands_is_str:
            return responses[0]

        log.debug("Host %s: Successfully executed command 'show' with responses %s.", self.host, responses)
        return responses
