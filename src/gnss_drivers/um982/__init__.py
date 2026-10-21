"""Unicore UM982 dual-antenna RTK receiver."""

from gnss_drivers.um982.driver import (
    DEFAULT_BAUD_RATE,
    DEFAULT_READ_TIMEOUT_S,
    MODULE_INIT_COMMANDS,
    UM982,
    InitTiming,
    UM982ReadError,
)

__all__ = [
    "DEFAULT_BAUD_RATE",
    "DEFAULT_READ_TIMEOUT_S",
    "MODULE_INIT_COMMANDS",
    "UM982",
    "InitTiming",
    "UM982ReadError",
]
