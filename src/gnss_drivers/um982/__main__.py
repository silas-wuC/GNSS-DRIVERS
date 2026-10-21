"""Read position and heading from a UM982 over a serial port."""

import argparse
import sys
import time

import serial

from gnss_drivers.fix import format_fix_line
from gnss_drivers.nmea import PARSED_SENTENCE_NAMES, update_fix_from_sentence
from gnss_drivers.serial_port import list_serial_ports
from gnss_drivers.um982.driver import (
    DEFAULT_BAUD_RATE,
    UM982,
    UM982ReadError,
)

STATUS_LINE_PAD_CHARS = 24
# A wrong baud rate yields silence rather than an error, so say so instead of
# letting the operator stare at an empty terminal.
NO_DATA_WARN_AFTER_S = 5.0


def print_serial_ports() -> None:
    port_rows = list_serial_ports()
    if not port_rows:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for device, description in port_rows:
        print("  " + device + "  " + description)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read GNSS position and heading from a Unicore UM982."
    )
    parser.add_argument(
        "--port",
        default="",
        help="Serial port name, e.g. COM29 or /dev/ttyUSB0. Omit to list.",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD_RATE,
        help=f"Baud rate (default {DEFAULT_BAUD_RATE}).",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="Print each unparsed NMEA sentence type once.",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        help="Skip init commands when the config is already stored.",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Persist the config to flash; flash endurance is limited.",
    )
    return parser.parse_args()


def run_read_loop(receiver: UM982, dump_unparsed: bool) -> None:
    seen_unparsed = set()
    started_at_s = time.monotonic()
    warned_about_silence = False
    while True:
        sentence = receiver.read_sentence()
        if sentence is None:
            silent_for_s = time.monotonic() - started_at_s
            stayed_silent = silent_for_s > NO_DATA_WARN_AFTER_S
            if stayed_silent and not warned_about_silence:
                print(
                    "\nNo valid NMEA yet; check the baud rate "
                    "(module default is 115200)."
                )
                warned_about_silence = True
            continue
        sentence_name = update_fix_from_sentence(sentence, receiver.fix)
        if sentence_name is None:
            continue
        started_at_s = time.monotonic()
        if sentence_name not in PARSED_SENTENCE_NAMES:
            if dump_unparsed and sentence_name not in seen_unparsed:
                seen_unparsed.add(sentence_name)
                print("\nDUMP " + sentence_name + ": " + sentence[:80])
            continue
        status_line = format_fix_line(receiver.fix)
        sys.stdout.write("\r" + status_line + (" " * STATUS_LINE_PAD_CHARS))
        sys.stdout.flush()


def main() -> int:
    args = parse_args()
    if not args.port:
        print_serial_ports()
        return 0

    receiver = UM982(args.port, baud_rate=args.baud)
    try:
        receiver.open()
    except serial.SerialException as exc:
        print("Failed to open " + args.port + ": " + str(exc))
        return 1

    try:
        if not args.no_init:
            for progress_text in receiver.apply_init_commands(
                save_to_flash=args.save_config
            ):
                print("Init " + progress_text)
            print("Init done.")
        print(
            "Reading " + args.port + " at " + str(args.baud)
            + " baud. Ctrl+C to stop."
        )
        run_read_loop(receiver, args.dump)
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
