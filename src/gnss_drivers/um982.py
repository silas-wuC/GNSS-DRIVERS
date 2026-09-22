"""Unicore UM982 serial transport and start-up sequence."""

import time
from typing import Iterator, List, Optional

import serial

from gnss_drivers.fix import GnssFix
from gnss_drivers.nmea import PARSED_SENTENCE_NAMES, update_fix_from_sentence
from gnss_drivers.serial_port import resolve_port_path

DEFAULT_BAUD_RATE = 230400
DEFAULT_READ_TIMEOUT_S = 1.0
INIT_CMD_DELAY_S = 0.08
INIT_SAVECONFIG_SETTLE_S = 0.35
INIT_DRAIN_LINES_MAX = 3
INIT_DRAIN_READ_TIMEOUT_S = 0.05
SAVECONFIG_COMMAND = "SAVECONFIG"

# KSXT is enabled but not parsed yet; it is left on so --dump can capture a
# real sample to write the parser against. Drop it once that is done.
MODULE_INIT_COMMANDS: List[str] = [
    "UNLOGCOM",
    "CONFIG MODE UAV",
    "CONFIG HEADING FIXLENGTH",
    "CONFIG NMEA GGA ONCHANGED 0.05",
    "CONFIG NMEA RMC ONCHANGED 0.05",
    "CONFIG NMEA THS ONCHANGED 0.05",
    "CONFIG NMEA VTG ONCHANGED 0.05",
    "CONFIG NMEA GSV ONCHANGED 1",
    "CONFIG NMEA GSA ONCHANGED 1",
    "CONFIG NMEA GST ONCHANGED 1",
    "KSXT 0.05",
]

# A dead port can return empty reads forever instead of raising, so cap how
# many in a row we tolerate before giving up.
EMPTY_READ_LIMIT = 10


class UM982ReadError(Exception):
    """Raised when the port stops delivering data, typically unplugged."""


class UM982:
    def __init__(
        self,
        port_name: str,
        baud_rate: int = DEFAULT_BAUD_RATE,
        read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
    ) -> None:
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.read_timeout_s = read_timeout_s
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

    def _drain_responses(self) -> None:
        port = self._require_port()
        read_timeout_prev = port.timeout
        port.timeout = INIT_DRAIN_READ_TIMEOUT_S
        try:
            for _ in range(INIT_DRAIN_LINES_MAX):
                if not port.readline():
                    break
        finally:
            port.timeout = read_timeout_prev

    def apply_init_commands(
        self, save_to_flash: bool = False
    ) -> Iterator[str]:
        """Send the start-up sequence, yielding one progress line each.

        save_to_flash defaults to False because the settings survive in flash
        once written, and rewriting identical config on every run only spends
        the module's limited flash endurance.
        """
        port = self._require_port()
        port.reset_input_buffer()
        commands = list(MODULE_INIT_COMMANDS)
        if save_to_flash:
            commands.append(SAVECONFIG_COMMAND)
        command_total = len(commands)
        for command_idx, command_text in enumerate(commands, start=1):
            self.send_command(command_text)
            self._drain_responses()
            if command_text == SAVECONFIG_COMMAND:
                time.sleep(INIT_SAVECONFIG_SETTLE_S)
            else:
                time.sleep(INIT_CMD_DELAY_S)
            yield f"{command_idx}/{command_total} {command_text}"

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
                if empty_read_count >= EMPTY_READ_LIMIT:
                    raise UM982ReadError(
                        "no data after "
                        f"{EMPTY_READ_LIMIT} reads; check the cable"
                    )
                continue
            empty_read_count = 0
            sentence_name = update_fix_from_sentence(sentence, self._fix)
            if sentence_name in PARSED_SENTENCE_NAMES:
                yield self._fix
