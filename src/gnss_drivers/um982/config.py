"""TOML settings for the UM982 command-line reader.

Precedence is fixed: command-line flags, then the config file, then the
code defaults. The driver never reads files itself, so it stays testable
with a fake port and usable from scripts that bring their own settings.
"""

import dataclasses
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:
    # tomllib only ships with Python 3.11 and later.
    import tomli as tomllib

from gnss_drivers.um982.driver import (
    DEFAULT_BAUD_RATE,
    DEFAULT_READ_TIMEOUT_S,
    EMPTY_READ_LIMIT,
    INIT_CMD_DELAY_S,
    INIT_DRAIN_LINES_MAX,
    INIT_DRAIN_READ_TIMEOUT_S,
    INIT_SAVECONFIG_SETTLE_S,
    MODULE_INIT_COMMANDS,
    SAVECONFIG_COMMAND,
    InitTiming,
)

# Relative on purpose: each bench keeps its own file next to where it runs.
DEFAULT_CONFIG_PATH = "um982.toml"
# A wrong baud rate yields silence rather than an error, so the reader
# warns after this long without a valid sentence.
NO_DATA_WARN_AFTER_S = 5.0


class UM982ConfigError(Exception):
    """Raised for a missing, malformed or out-of-range config."""


@dataclass
class UM982Config:
    """Every setting the reader takes; field names match the CLI flags."""

    port: str = ""
    baud: int = DEFAULT_BAUD_RATE
    read_timeout_s: float = DEFAULT_READ_TIMEOUT_S
    dump: bool = False
    init: bool = True
    save_config: bool = False
    no_data_warn_after_s: float = NO_DATA_WARN_AFTER_S
    empty_read_limit: int = EMPTY_READ_LIMIT
    init_cmd_delay_s: float = INIT_CMD_DELAY_S
    init_saveconfig_settle_s: float = INIT_SAVECONFIG_SETTLE_S
    init_drain_lines_max: int = INIT_DRAIN_LINES_MAX
    init_drain_read_timeout_s: float = INIT_DRAIN_READ_TIMEOUT_S
    init_commands: List[str] = field(
        default_factory=lambda: list(MODULE_INIT_COMMANDS)
    )

    def init_timing(self) -> InitTiming:
        return InitTiming(
            cmd_delay_s=self.init_cmd_delay_s,
            saveconfig_settle_s=self.init_saveconfig_settle_s,
            drain_lines_max=self.init_drain_lines_max,
            drain_read_timeout_s=self.init_drain_read_timeout_s,
        )


# TOML section -> key -> (UM982Config field name, expected type).
CONFIG_KEYS = {
    "serial": {
        "port": ("port", str),
        "baud": ("baud", int),
        "read_timeout_s": ("read_timeout_s", float),
    },
    "run": {
        "dump": ("dump", bool),
        "init": ("init", bool),
        "save_config": ("save_config", bool),
        "no_data_warn_after_s": ("no_data_warn_after_s", float),
        "empty_read_limit": ("empty_read_limit", int),
    },
    "init": {
        "cmd_delay_s": ("init_cmd_delay_s", float),
        "saveconfig_settle_s": ("init_saveconfig_settle_s", float),
        "drain_lines_max": ("init_drain_lines_max", int),
        "drain_read_timeout_s": ("init_drain_read_timeout_s", float),
        "commands": ("init_commands", list),
    },
}


def check_value_type(key_path: str, value, expected_type):
    """Return value as expected_type, or raise naming the offending key."""
    # bool is a subclass of int, so "baud = true" would otherwise pass.
    if isinstance(value, bool) and expected_type is not bool:
        raise UM982ConfigError(
            f"{key_path}: expected {expected_type.__name__}, got bool"
        )
    # TOML writes "delay = 1" as an int; refusing it would only annoy.
    if expected_type is float and isinstance(value, int):
        return float(value)
    if not isinstance(value, expected_type):
        raise UM982ConfigError(
            f"{key_path}: expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )
    if expected_type is list:
        for entry in value:
            if not isinstance(entry, str):
                raise UM982ConfigError(
                    f"{key_path}: every entry must be a string"
                )
        return list(value)
    return value


def apply_toml_values(config: UM982Config, toml_doc: dict) -> None:
    # Unknown keys are errors because a typo such as "buad" would otherwise
    # be skipped silently and the run would use the default instead.
    for section_name, section_values in toml_doc.items():
        if section_name not in CONFIG_KEYS:
            raise UM982ConfigError(f"unknown section [{section_name}]")
        if not isinstance(section_values, dict):
            raise UM982ConfigError(
                f"{section_name}: expected a [{section_name}] table"
            )
        section_keys = CONFIG_KEYS[section_name]
        for key_name, value in section_values.items():
            key_path = section_name + "." + key_name
            if key_name not in section_keys:
                raise UM982ConfigError(key_path + ": unknown key")
            field_name, expected_type = section_keys[key_name]
            checked_value = check_value_type(key_path, value, expected_type)
            setattr(config, field_name, checked_value)


def load_config_file(
    config_path: Optional[str],
) -> Tuple[UM982Config, str]:
    """Return the config plus a one-line note on where it came from.

    Only the default path may be absent. A path the user named explicitly
    must exist, otherwise a typo would quietly fall back to defaults.
    """
    config = UM982Config()
    if config_path is None:
        path_text = DEFAULT_CONFIG_PATH
        if not os.path.isfile(path_text):
            return config, path_text + " not found, using defaults"
    else:
        path_text = config_path
        if not os.path.isfile(path_text):
            raise UM982ConfigError(path_text + ": file not found")
    try:
        with open(path_text, "rb") as config_file:
            toml_doc = tomllib.load(config_file)
        apply_toml_values(config, toml_doc)
    except (tomllib.TOMLDecodeError, UM982ConfigError) as exc:
        raise UM982ConfigError(path_text + ": " + str(exc)) from None
    return config, path_text


def apply_cli_overrides(config: UM982Config, cli_values: dict) -> None:
    """Copy every flag the user actually passed; None means not passed."""
    for config_field in dataclasses.fields(config):
        cli_value = cli_values.get(config_field.name)
        if cli_value is None:
            continue
        setattr(config, config_field.name, cli_value)


def validate_config(config: UM982Config) -> None:
    """Range checks, run after merging so file and flags obey one rule."""
    if config.baud <= 0:
        raise UM982ConfigError("baud must be > 0")
    # pyserial treats a zero timeout as non-blocking, which returns partial
    # lines and turns every idle moment into an empty read.
    if config.read_timeout_s <= 0:
        raise UM982ConfigError("read_timeout_s must be > 0")
    if config.init_drain_read_timeout_s <= 0:
        raise UM982ConfigError("init_drain_read_timeout_s must be > 0")
    non_negative_fields = [
        "no_data_warn_after_s",
        "empty_read_limit",
        "init_cmd_delay_s",
        "init_saveconfig_settle_s",
        "init_drain_lines_max",
    ]
    for field_name in non_negative_fields:
        if getattr(config, field_name) < 0:
            raise UM982ConfigError(field_name + " must be >= 0")
    if not config.init_commands:
        raise UM982ConfigError("init.commands must not be empty")
    for command_text in config.init_commands:
        command_words = command_text.split()
        if not command_words:
            raise UM982ConfigError("init.commands has a blank entry")
        # Writing flash on every start-up burns the module's limited
        # endurance; save_config sends it once, only when asked.
        if command_words[0].upper() == SAVECONFIG_COMMAND:
            raise UM982ConfigError(
                "init.commands must not contain SAVECONFIG; "
                "set run.save_config = true instead"
            )
