"""Serial port helpers that are transport concerns, not device concerns."""

import sys
from typing import List, Tuple

import serial.tools.list_ports


def list_serial_ports() -> List[Tuple[str, str]]:
    """Return (device, description) pairs; printing belongs to the caller."""
    port_rows = []
    for port_info in serial.tools.list_ports.comports():
        port_rows.append((port_info.device, port_info.description))
    return port_rows


def resolve_port_path(port_name: str) -> str:
    """Expand COM10 and above to the Win32 device path pyserial requires.

    Guarded on the platform so a Linux device that happens to be named COM*
    by a udev rule is left alone.
    """
    if not sys.platform.startswith("win"):
        return port_name
    if not port_name.upper().startswith("COM"):
        return port_name
    com_digits = port_name[3:]
    if not com_digits.isdigit():
        return port_name
    if int(com_digits) < 10:
        return port_name
    return "\\\\.\\" + port_name
