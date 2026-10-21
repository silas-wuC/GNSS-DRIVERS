"""Receiver state shared by all NMEA sentence parsers."""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class GnssFix:
    """Latest known receiver state.

    A single NMEA sentence never carries a complete fix: GGA brings
    position, GSA brings DOP, THS brings heading, KSXT brings heading
    quality. Parsers therefore update this object in place and callers read
    whatever the receiver has said so far.
    """

    utc_text: Optional[str] = None
    lat_deg: Optional[float] = None
    lon_deg: Optional[float] = None
    alt_msl_m: Optional[float] = None
    alt_hae_m: Optional[float] = None
    sats_used: Optional[int] = None
    hdop: Optional[float] = None
    vdop: Optional[float] = None
    yaw_deg: Optional[float] = None
    # GGA quality indicator, Unicore N4 manual Table 7-4: 4 = RTK fixed,
    # 5 = RTK float.
    position_quality: Optional[int] = None
    # KSXT heading quality, manual Table 7-107: 3 = RTK fixed, 2 = RTK
    # float. The numbering differs from GGA, so never compare the two.
    heading_quality: Optional[int] = None
    # Satellites the ANT2 (slave) solution uses; 0 explains a missing
    # heading before anyone suspects the firmware.
    ant2_sats_used: Optional[int] = None

    def clear_position(self) -> None:
        """Drop position while keeping time and satellite bookkeeping.

        GGA still reports a valid UTC and satellite count when quality is 0,
        so only the coordinates and altitudes become meaningless.
        """
        self.lat_deg = None
        self.lon_deg = None
        self.alt_msl_m = None
        self.alt_hae_m = None


# GGA quality indicator, Unicore N4 manual Table 7-4.
POSITION_QUALITY_NAMES: Dict[int, str] = {
    0: "NONE",
    1: "SINGLE",
    2: "DGPS",
    3: "PPS",
    4: "FIXED",
    5: "FLOAT",
    6: "DR",
    7: "MANUAL",
    8: "SIM",
}
# KSXT heading quality, manual Table 7-107. Not the GGA numbering: here
# 3 is fixed and 2 is float.
HEADING_QUALITY_NAMES: Dict[int, str] = {
    0: "NONE",
    1: "SINGLE",
    2: "FLOAT",
    3: "FIXED",
}


def format_quality(
    quality_code: Optional[int], quality_names: Dict[int, str]
) -> str:
    if quality_code is None:
        return "--"
    if quality_code in quality_names:
        return quality_names[quality_code]
    # A code missing from the manual table, e.g. from newer firmware, is
    # shown raw instead of being dropped or given a wrong name.
    return "Q" + str(quality_code)


def format_optional_number(value: Optional[float], decimal_digits: int) -> str:
    if value is None:
        return "--"
    return f"{value:.{decimal_digits}f}"


def format_fix_line(fix: GnssFix) -> str:
    """One-line status suitable for overwriting in place on a terminal."""
    utc_text = fix.utc_text
    if utc_text is None:
        utc_text = "--"
    if fix.sats_used is None:
        sats_text = "--"
    else:
        sats_text = str(fix.sats_used)
    if fix.ant2_sats_used is None:
        ant2_sats_text = "--"
    else:
        ant2_sats_text = str(fix.ant2_sats_used)
    position_quality_text = format_quality(
        fix.position_quality, POSITION_QUALITY_NAMES
    )
    heading_quality_text = format_quality(
        fix.heading_quality, HEADING_QUALITY_NAMES
    )
    return (
        f"UTC {utc_text}"
        f"  RTK {position_quality_text}"
        f"  LAT {format_optional_number(fix.lat_deg, 6)}"
        f"  LON {format_optional_number(fix.lon_deg, 6)}"
        f"  ALT_MSL {format_optional_number(fix.alt_msl_m, 1)} m"
        f"  ALT_HAE {format_optional_number(fix.alt_hae_m, 1)} m"
        f"  SATS {sats_text}"
        f"  HDOP {format_optional_number(fix.hdop, 1)}"
        f"  VDOP {format_optional_number(fix.vdop, 1)}"
        f"  YAW {format_optional_number(fix.yaw_deg, 1)}"
        f"  HDG {heading_quality_text}"
        f"  ANT2 {ant2_sats_text}"
    )
