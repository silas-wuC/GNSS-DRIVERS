import pytest

from conftest import (
    GGA_RTK_FIXED,
    GSA_WITH_SYSTEM_ID,
    KSXT_NO_HEADING,
    THS_VALID,
    UNPARSED_SENTENCES,
)
from gnss_drivers import nmea


def test_checksum_accepts_known_good_sentences():
    assert nmea.checksum_ok(GGA_RTK_FIXED)
    assert nmea.checksum_ok(GSA_WITH_SYSTEM_ID)
    assert nmea.checksum_ok(THS_VALID)


def test_checksum_accepts_lowercase_hex():
    # Receivers are inconsistent about checksum case, so accept both.
    assert nmea.checksum_ok("$GNVTG,,T,,M,0.024,N,0.044,K,D*3E")
    assert nmea.checksum_ok("$GNVTG,,T,,M,0.024,N,0.044,K,D*3e")


def test_checksum_rejects_corrupt_sentences():
    assert not nmea.checksum_ok("$GNTHS,123.45,A*19")
    assert not nmea.checksum_ok("$GNTHS,123.45,A*1")
    assert not nmea.checksum_ok("$GNTHS,123.45,A")
    assert not nmea.checksum_ok("$GNTHS,123.45,A*ZZ")


def test_sentence_type_is_talker_agnostic():
    assert nmea.sentence_type("$GNGGA,1,2*00") == "GGA"
    assert nmea.sentence_type("$GPGGA,1,2*00") == "GGA"
    assert nmea.sentence_type("$GPGSA,1,2*00") == "GSA"


def test_sentence_type_keeps_proprietary_name_intact():
    # Trimming to three characters would yield "SXT" and break dispatch.
    assert nmea.sentence_type(KSXT_NO_HEADING) == "KSXT"


def test_latlon_conversion_handles_hemispheres():
    assert nmea.latlon_to_deg("2503.7458570", "N") == pytest.approx(
        25.06243095
    )
    assert nmea.latlon_to_deg("2503.7458570", "S") == pytest.approx(
        -25.06243095
    )
    assert nmea.latlon_to_deg("12134.8712341", "E") == pytest.approx(
        121.581187235
    )
    assert nmea.latlon_to_deg("12134.8712341", "W") == pytest.approx(
        -121.581187235
    )
    assert nmea.latlon_to_deg("", "N") is None


def test_format_utc():
    assert nmea.format_utc("062133.000") == "06:21:33.000"
    assert nmea.format_utc("062133") == "06:21:33"
    assert nmea.format_utc("") is None
    assert nmea.format_utc("abc") is None


def test_optional_number_parsers_tolerate_empty_fields():
    assert nmea.parse_optional_float("") is None
    assert nmea.parse_optional_float("bad") is None
    assert nmea.parse_optional_float("1.5") == pytest.approx(1.5)
    assert nmea.parse_optional_int("") is None
    assert nmea.parse_optional_int("bad") is None
    assert nmea.parse_optional_int("28") == 28


def test_unparsed_sentences_are_named_but_not_applied():
    for sentence in UNPARSED_SENTENCES:
        sentence_name = nmea.sentence_type(sentence)
        assert sentence_name not in nmea.PARSED_SENTENCE_NAMES
        assert nmea.checksum_ok(sentence)
