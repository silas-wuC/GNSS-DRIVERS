"""Read position and heading from a UM982 over a serial port."""

import argparse
import sys
import time
from typing import List, Optional, Tuple

import serial

from gnss_drivers.fix import format_fix_line
from gnss_drivers.nmea import PARSED_SENTENCE_NAMES, update_fix_from_sentence
from gnss_drivers.serial_port import list_serial_ports
from gnss_drivers.um982.config import (
    DEFAULT_CONFIG_PATH,
    UM982Config,
    UM982ConfigError,
    apply_cli_overrides,
    load_config_file,
    validate_config,
)
from gnss_drivers.um982.driver import UM982, UM982ReadError

STATUS_LINE_PAD_CHARS = 24


def print_serial_ports() -> None:
    port_rows = list_serial_ports()
    if not port_rows:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for device, description in port_rows:
        print("  " + device + "  " + description)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    # Every default is None so an absent flag never masks the config file;
    # the real defaults live in UM982Config and are only shown in help.
    defaults = UM982Config()
    parser = argparse.ArgumentParser(
        prog="python -m gnss_drivers.um982",
        description="Read GNSS position and heading from a Unicore UM982.",
        epilog="Precedence: flags, then the config file, then defaults.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help=f"TOML config path (default ./{DEFAULT_CONFIG_PATH} if any).",
    )
    parser.add_argument(
        "--port",
        default=None,
        help="Serial port name, e.g. COM29 or /dev/ttyUSB0. Omit to list.",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=None,
        help=f"Baud rate (default {defaults.baud}).",
    )
    parser.add_argument(
        "--read-timeout-s",
        type=float,
        default=None,
        help=f"Serial read timeout (default {defaults.read_timeout_s}).",
    )
    # BooleanOptionalAction adds --no-X, which plain store_true cannot do,
    # so a flag can switch off what the config file switched on.
    parser.add_argument(
        "--dump",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print each unparsed NMEA sentence type once (default off).",
    )
    parser.add_argument(
        "--init",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Send init commands; --no-init when already stored "
        "(default on).",
    )
    parser.add_argument(
        "--save-config",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Persist the config to flash; flash endurance is limited "
        "(default off).",
    )
    parser.add_argument(
        "--no-data-warn-after-s",
        type=float,
        default=None,
        help="Warn about baud mismatch after this long "
        f"(default {defaults.no_data_warn_after_s}).",
    )
    parser.add_argument(
        "--empty-read-limit",
        type=int,
        default=None,
        help="Exit after this many empty reads, 0 never "
        f"(default {defaults.empty_read_limit}).",
    )
    parser.add_argument(
        "--init-cmd-delay-s",
        type=float,
        default=None,
        help="Pause after each init command "
        f"(default {defaults.init_cmd_delay_s}).",
    )
    parser.add_argument(
        "--init-saveconfig-settle-s",
        type=float,
        default=None,
        help="Pause after SAVECONFIG "
        f"(default {defaults.init_saveconfig_settle_s}).",
    )
    parser.add_argument(
        "--init-drain-lines-max",
        type=int,
        default=None,
        help="Lines read back per init command "
        f"(default {defaults.init_drain_lines_max}).",
    )
    parser.add_argument(
        "--init-drain-read-timeout-s",
        type=float,
        default=None,
        help="Read timeout while draining replies "
        f"(default {defaults.init_drain_read_timeout_s}).",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> Tuple[UM982Config, str]:
    config, config_note = load_config_file(args.config)
    apply_cli_overrides(config, vars(args))
    validate_config(config)
    return config, config_note


def run_read_loop(receiver: UM982, config: UM982Config) -> None:
    seen_unparsed = set()
    started_at_s = time.monotonic()
    warned_about_silence = False
    empty_read_count = 0
    while True:
        sentence = receiver.read_sentence()
        if sentence is None:
            # Zero bytes, unlike a wrong baud rate, means nothing is talking
            # at all, so give up the same way UM982.read_fixes() does.
            empty_read_count += 1
            limit_reached = (
                config.empty_read_limit > 0
                and empty_read_count >= config.empty_read_limit
            )
            if limit_reached:
                raise UM982ReadError(
                    "no data after "
                    f"{config.empty_read_limit} reads; check the cable"
                )
            silent_for_s = time.monotonic() - started_at_s
            stayed_silent = silent_for_s > config.no_data_warn_after_s
            if stayed_silent and not warned_about_silence:
                print(
                    "\nNo valid NMEA yet; check the baud rate "
                    "(module default is 115200)."
                )
                warned_about_silence = True
            continue
        empty_read_count = 0
        sentence_name = update_fix_from_sentence(sentence, receiver.fix)
        if sentence_name is None:
            continue
        started_at_s = time.monotonic()
        if sentence_name not in PARSED_SENTENCE_NAMES:
            if config.dump and sentence_name not in seen_unparsed:
                seen_unparsed.add(sentence_name)
                print("\nDUMP " + sentence_name + ": " + sentence[:80])
            continue
        status_line = format_fix_line(receiver.fix)
        sys.stdout.write("\r" + status_line + (" " * STATUS_LINE_PAD_CHARS))
        sys.stdout.flush()


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        config, config_note = build_config(args)
    except UM982ConfigError as exc:
        print("Config error: " + str(exc))
        return 1
    # The default path is relative to the working directory, so say which
    # file was used; running from elsewhere silently means defaults.
    print("Config: " + config_note)
    if not config.port:
        print_serial_ports()
        return 0
    if config.save_config and not config.init:
        print("Warning: save_config ignored because init is off.")

    receiver = UM982(
        config.port,
        baud_rate=config.baud,
        read_timeout_s=config.read_timeout_s,
        empty_read_limit=config.empty_read_limit,
        init_timing=config.init_timing(),
    )
    try:
        receiver.open()
    except serial.SerialException as exc:
        print("Failed to open " + config.port + ": " + str(exc))
        return 1

    try:
        if config.init:
            for progress_text in receiver.apply_init_commands(
                save_to_flash=config.save_config,
                init_commands=config.init_commands,
            ):
                print("Init " + progress_text)
            print("Init done.")
        print(
            "Reading " + config.port + " at " + str(config.baud)
            + " baud. Ctrl+C to stop."
        )
        run_read_loop(receiver, config)
    except KeyboardInterrupt:
        print("\nStopped.")
    except UM982ReadError as exc:
        print("\nRead failed: " + str(exc))
        return 1
    finally:
        receiver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
