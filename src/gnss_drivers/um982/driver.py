"""Unicore UM982 serial transport and start-up sequence."""

import time
from dataclasses import dataclass
from typing import Iterator, List, Optional

import serial

from gnss_drivers.fix import GnssFix
from gnss_drivers.nmea import PARSED_SENTENCE_NAMES, update_fix_from_sentence
from gnss_drivers.serial_port import resolve_port_path

DEFAULT_BAUD_RATE = 230400
DEFAULT_READ_TIMEOUT_S = 1.0
INIT_CMD_DELAY_S = 0.08
INIT_SAVECONFIG_SETTLE_S = 0.35
INIT_REPLY_TIMEOUT_S = 5.0
INIT_DRAIN_READ_TIMEOUT_S = 0.05
SAVECONFIG_COMMAND = "SAVECONFIG"
# Unicore N4 receivers echo each command as "$command,<text>,response: OK",
# or "response: PARSING FAILED <reason>" when they reject it.
COMMAND_REPLY_PREFIX = "$command,"
COMMAND_REPLY_MARKER = ",response:"
COMMAND_REPLY_OK = "response: OK"

# Syntax follows the Unicore N4 commands manual R1.15. Log requests must use
# the GP prefix whatever talker the output carries, and leave out the port so
# the output goes to the port the command arrived on.
# KSXT is enabled but not parsed yet; it is left on so --dump can capture a
# real sample to write the parser against. Drop it once that is done.
MODULE_INIT_COMMANDS: List[str] = [
    "UNLOG",
    "MODE ROVER UAV",
    "CONFIG HEADING FIXLENGTH",
    "CONFIG SMOOTH HEADING 0",
    "GPGGA 0.05",
    "GPRMC 0.05",
    "GPTHS 0.05",
    "GPVTG 0.05",
    "GPGSV 1",
    "GPGSA 1",
    "GPGST 1",
    "KSXT 0.05",
]

# A dead port can return empty reads forever instead of raising, so cap how
# many in a row we tolerate before giving up.
EMPTY_READ_LIMIT = 10


class UM982ReadError(Exception):
    """Raised when the port stops delivering data, typically unplugged."""


class UM982InitError(Exception):
    """Raised when the module rejects an init command or never answers."""


@dataclass
class InitTiming:
    """Pacing for the start-up command sequence."""

    cmd_delay_s: float = INIT_CMD_DELAY_S
    saveconfig_settle_s: float = INIT_SAVECONFIG_SETTLE_S
    reply_timeout_s: float = INIT_REPLY_TIMEOUT_S
    drain_read_timeout_s: float = INIT_DRAIN_READ_TIMEOUT_S


def reply_status_text(reply_line: str) -> str:
    """Turn "$command,X,response: OK*5C" into "response: OK".

    Cut at the marker, not at the last comma: a rejection reason can hold
    commas itself, e.g. "PARSING FAILED FIELD OUT OF RANGE,300".
    """
    reply_body = reply_line.split("*", 1)[0]
    marker_idx = reply_body.find(COMMAND_REPLY_MARKER)
    if marker_idx < 0:
        return reply_body.strip()
    return reply_body[marker_idx + 1:].strip()


class UM982:
    def __init__(
        self,
        port_name: str,
        baud_rate: int = DEFAULT_BAUD_RATE,
        read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
        empty_read_limit: int = EMPTY_READ_LIMIT,
        init_timing: Optional[InitTiming] = None,
    ) -> None:
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.read_timeout_s = read_timeout_s
        self.empty_read_limit = empty_read_limit
        if init_timing is None:
            init_timing = InitTiming()
        self.init_timing = init_timing
        self._serial: Optional[serial.Serial] = None
        self._fix = GnssFix()

    @property
    def fix(self) -> GnssFix:
        return self._fix

    def open(self) -> None:
        # Opening here rather than in __init__ keeps a failed port from
        # leaving a half-built object with no way to close it.
        self._serial = serial.Serial(
            port=resolve_port_path(self.port_name),
            baudrate=self.baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.read_timeout_s,
        )

    def close(self) -> None:
        if self._serial is None:
            return
        self._serial.close()
        self._serial = None

    def __enter__(self) -> "UM982":
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _require_port(self) -> serial.Serial:
        if self._serial is None:
            raise UM982ReadError("port is not open; call open() first")
        return self._serial

    def send_command(self, command_text: str) -> None:
        port = self._require_port()
        port.write((command_text + "\r\n").encode("ascii"))
        port.flush()

    def _wait_for_reply(self) -> Optional[str]:
        """Return the command's reply line, or None if time runs out.

        Without this a rejected command is indistinguishable from an
        accepted one, because the module keeps streaming NMEA either way.
        The wait is bounded by time, not by line count: the reply queues
        behind everything the module had already buffered for output, and
        an overloaded log list leaves seconds of it.
        """
        port = self._require_port()
        read_timeout_prev = port.timeout
        port.timeout = self.init_timing.drain_read_timeout_s
        deadline_s = time.monotonic() + self.init_timing.reply_timeout_s
        try:
            while time.monotonic() < deadline_s:
                raw_line = port.readline()
                if not raw_line:
                    continue
                line_text = raw_line.decode("ascii", errors="ignore").strip()
                if line_text.startswith(COMMAND_REPLY_PREFIX):
                    return line_text
        finally:
            port.timeout = read_timeout_prev
        return None

    def apply_init_commands(
        self,
        save_to_flash: bool = False,
        init_commands: Optional[List[str]] = None,
    ) -> Iterator[str]:
        """Send the start-up sequence, yielding one progress line each.

        save_to_flash defaults to False because the settings survive in flash
        once written, and rewriting identical config on every run only spends
        the module's limited flash endurance.

        Raises UM982InitError at the first command the module rejects or
        does not answer within reply_timeout_s. Carrying on would leave the
        module on whatever its flash holds while the caller believes its own
        list is in effect. Commands sent before the failure stay applied.
        """
        port = self._require_port()
        port.reset_input_buffer()
        if init_commands is None:
            commands = list(MODULE_INIT_COMMANDS)
        else:
            commands = list(init_commands)
        if save_to_flash:
            commands.append(SAVECONFIG_COMMAND)
        command_total = len(commands)
        for command_idx, command_text in enumerate(commands, start=1):
            self.send_command(command_text)
            reply_line = self._wait_for_reply()
            if reply_line is None:
                raise UM982InitError(
                    f"{command_text}: no reply within "
                    f"{self.init_timing.reply_timeout_s} s; "
                    "check the baud rate"
                )
            reply_text = reply_status_text(reply_line)
            if reply_text != COMMAND_REPLY_OK:
                raise UM982InitError(command_text + ": " + reply_text)
            if command_text == SAVECONFIG_COMMAND:
                time.sleep(self.init_timing.saveconfig_settle_s)
            else:
                time.sleep(self.init_timing.cmd_delay_s)
            yield (
                f"{command_idx}/{command_total} {command_text}"
                f" -> {reply_text}"
            )

    def read_sentence(self) -> Optional[str]:
        """Return one sentence, or None when the read timed out."""
        port = self._require_port()
        raw_line = port.readline()
        if not raw_line:
            return None
        return raw_line.decode("ascii", errors="ignore").strip()

    def read_fixes(self) -> Iterator[GnssFix]:
        """Yield the fix whenever a parsed sentence updates it.

        The same GnssFix object is yielded every time because a fix is the
        receiver's current state rather than a discrete event. Callers that
        want a snapshot must copy it with dataclasses.replace().
        """
        empty_read_count = 0
        while True:
            sentence = self.read_sentence()
            if sentence is None:
                empty_read_count += 1
                # 0 disables the limit so a bench can wait for a late
                # power-up instead of exiting.
                limit_reached = (
                    self.empty_read_limit > 0
                    and empty_read_count >= self.empty_read_limit
                )
                if limit_reached:
                    raise UM982ReadError(
                        "no data after "
                        f"{self.empty_read_limit} reads; check the cable"
                    )
                continue
            empty_read_count = 0
            sentence_name = update_fix_from_sentence(sentence, self._fix)
            if sentence_name in PARSED_SENTENCE_NAMES:
                yield self._fix
