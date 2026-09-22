"""Stateless NMEA sentence parsing.

This module never touches a serial port or stdout so that every function
here is testable from a plain string, and so recorded logs can be replayed
offline without faking a transport.
"""

from typing import List, Optional

from gnss_drivers.fix import GnssFix

# GSA always pads its satellite list to 12 slots, even when unused.
GSA_SAT_SLOT_COUNT = 12

# Sentences that carry no talker ID, so the "last three characters" rule
# used to fold GNGGA/GPGGA into GGA would mangle them instead.
PROPRIETARY_SENTENCE_NAMES = frozenset({"KSXT"})

# Sentence names this module understands well enough to update a fix.
PARSED_SENTENCE_NAMES = frozenset({"GGA", "GSA", "THS"})


def checksum_ok(sentence: str) -> bool:
    star_idx = sentence.find("*")
    if star_idx < 0:
        return False
    if star_idx + 3 > len(sentence):
        return False
    payload = sentence[1:star_idx]
    try:
        given_checksum = int(sentence[star_idx + 1:star_idx + 3], 16)
    except ValueError:
        return False
    calculated_checksum = 0
    for payload_char in payload:
        calculated_checksum ^= ord(payload_char)
    return calculated_checksum == given_checksum


def sentence_type(sentence: str) -> str:
    """Talker-agnostic sentence name, so GNGGA and GPGGA both give GGA."""
    comma_idx = sentence.find(",")
    if comma_idx < 0:
        header = sentence[1:]
    else:
        header = sentence[1:comma_idx]
    # Trimming a proprietary header to three characters would turn KSXT into
    # SXT and silently break dispatch for anyone adding a parser later.
    if header in PROPRIETARY_SENTENCE_NAMES:
        return header
    if len(header) < 3:
        return ""
    return header[-3:]


def split_fields(sentence: str) -> List[str]:
    return sentence.split("*", 1)[0].split(",")


def parse_optional_float(field_text: str) -> Optional[float]:
    if not field_text:
        return None
    try:
        return float(field_text)
    except ValueError:
        return None


def parse_optional_int(field_text: str) -> Optional[int]:
    if not field_text:
        return None
    try:
        return int(field_text)
    except ValueError:
        return None


def latlon_to_deg(nmea_coord_text: str, hemisphere: str) -> Optional[float]:
    """Convert DDMM.MMMM (or DDDMM.MMMM) to signed decimal degrees."""
    nmea_coord = parse_optional_float(nmea_coord_text)
    if nmea_coord is None:
        return None
    whole_degrees = int(nmea_coord / 100.0)
    minutes = nmea_coord - whole_degrees * 100.0
    decimal_deg = whole_degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        decimal_deg = -decimal_deg
    return decimal_deg


def format_utc(nmea_time_text: str) -> Optional[str]:
    """Convert hhmmss.sss to HH:MM:SS.sss."""
    if not nmea_time_text:
        return None
    if "." in nmea_time_text:
        whole_part, frac_part = nmea_time_text.split(".", 1)
    else:
        whole_part = nmea_time_text
        frac_part = ""
    if not whole_part.isdigit():
        return None
    whole_part = whole_part.zfill(6)
    utc_text = whole_part[0:2] + ":" + whole_part[2:4] + ":" + whole_part[4:6]
    if frac_part:
        utc_text = utc_text + "." + frac_part
    return utc_text


def parse_gga(fields: List[str], fix: GnssFix) -> None:
    """$GNGGA,utc,lat,N/S,lon,E/W,quality,sats,hdop,alt,M,geoid,M,..."""
    if len(fields) < 10:
        return
    # Time stays valid with no position fix, so record it before bailing out.
    fix.utc_text = format_utc(fields[1])
    fix.sats_used = parse_optional_int(fields[7])
    if fields[8]:
        fix.hdop = parse_optional_float(fields[8])
    quality = parse_optional_int(fields[6])
    if quality is None or quality == 0:
        fix.clear_position()
        return
    fix.lat_deg = latlon_to_deg(fields[2], fields[3])
    fix.lon_deg = latlon_to_deg(fields[4], fields[5])
    altitude_msl_m = parse_optional_float(fields[9])
    # Field 9 is height above mean sea level; field 11 is geoid separation.
    # Consumers expecting phone-style WGS84 altitude need the sum of both.
    geoid_separation_m = None
    if len(fields) >= 12:
        geoid_separation_m = parse_optional_float(fields[11])
    fix.alt_msl_m = altitude_msl_m
    if altitude_msl_m is None or geoid_separation_m is None:
        fix.alt_hae_m = None
    else:
        fix.alt_hae_m = altitude_msl_m + geoid_separation_m


def parse_gsa(fields: List[str], fix: GnssFix) -> None:
    """$GNGSA,mode,fix,sat1..sat12,pdop,hdop,vdop[,system_id]"""
    # The satellite slots are always padded to 12, so these offsets hold for
    # both NMEA 2.3 (18 fields) and NMEA 4.10, which appends system_id at the
    # tail. Do not "fix" these indices after spotting the extra field.
    hdop_field_idx = 3 + GSA_SAT_SLOT_COUNT + 1
    vdop_field_idx = hdop_field_idx + 1
    if len(fields) <= vdop_field_idx:
        return
    hdop = parse_optional_float(fields[hdop_field_idx])
    vdop = parse_optional_float(fields[vdop_field_idx])
    if hdop is not None:
        fix.hdop = hdop
    if vdop is not None:
        fix.vdop = vdop


def parse_ths(fields: List[str], fix: GnssFix) -> None:
    """$GNTHS,heading_deg,status -- status V means the heading is invalid."""
    if len(fields) < 3:
        return
    status_flag = fields[2]
    if status_flag == "V":
        fix.yaw_deg = None
        return
    fix.yaw_deg = parse_optional_float(fields[1])


def update_fix_from_sentence(sentence: str, fix: GnssFix) -> Optional[str]:
    """Apply one sentence to the fix.

    Returns None when the sentence is unusable, otherwise the sentence name.
    Callers compare against PARSED_SENTENCE_NAMES to tell an applied sentence
    from one that merely passed checksum, which keeps debug printing out of
    the parsing layer.
    """
    if not sentence.startswith("$"):
        return None
    if not checksum_ok(sentence):
        return None
    sentence_name = sentence_type(sentence)
    fields = split_fields(sentence)
    if sentence_name == "GGA":
        parse_gga(fields, fix)
    elif sentence_name == "GSA":
        parse_gsa(fields, fix)
    elif sentence_name == "THS":
        parse_ths(fields, fix)
    return sentence_name
