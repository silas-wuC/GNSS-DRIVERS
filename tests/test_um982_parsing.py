import pytest

from conftest import (
    GGA_NO_FIX,
    GGA_RTK_FIXED,
    GSA_ALL_SLOTS_USED,
    GSA_WITH_SYSTEM_ID,
    GSA_WITHOUT_SYSTEM_ID,
    KSXT_NO_HEADING,
    THS_INVALID,
    THS_VALID,
)
from gnss_drivers import GnssFix, update_fix_from_sentence


def test_gga_rtk_fix_populates_every_field():
    fix = GnssFix()
    assert update_fix_from_sentence(GGA_RTK_FIXED, fix) == "GGA"
    assert fix.utc_text == "06:21:33.000"
    assert fix.lat_deg == pytest.approx(25.06243095)
    assert fix.lon_deg == pytest.approx(121.581187235)
    assert fix.alt_msl_m == pytest.approx(45.123)
    # HAE is MSL plus geoid separation, which GGA carries in field 11.
    assert fix.alt_hae_m == pytest.approx(62.579)
    assert fix.sats_used == 28
    assert fix.hdop == pytest.approx(0.60)


def test_gga_without_fix_clears_position_but_keeps_time():
    fix = GnssFix()
    update_fix_from_sentence(GGA_RTK_FIXED, fix)
    assert update_fix_from_sentence(GGA_NO_FIX, fix) == "GGA"
    assert fix.lat_deg is None
    assert fix.lon_deg is None
    assert fix.alt_msl_m is None
    assert fix.alt_hae_m is None
    # Time and satellite bookkeeping survive a lost fix.
    assert fix.utc_text == "06:21:34.000"
    assert fix.sats_used == 4
    assert fix.hdop == pytest.approx(99.99)


@pytest.mark.parametrize(
    "sentence",
    [GSA_WITH_SYSTEM_ID, GSA_ALL_SLOTS_USED, GSA_WITHOUT_SYSTEM_ID],
)
def test_gsa_dop_offsets_hold_across_nmea_versions(sentence):
    fix = GnssFix()
    assert update_fix_from_sentence(sentence, fix) == "GSA"
    assert fix.hdop == pytest.approx(0.70)
    assert fix.vdop == pytest.approx(0.98)


def test_ths_valid_heading():
    fix = GnssFix()
    assert update_fix_from_sentence(THS_VALID, fix) == "THS"
    assert fix.yaw_deg == pytest.approx(123.45)


def test_ths_invalid_status_clears_stale_heading():
    fix = GnssFix()
    update_fix_from_sentence(THS_VALID, fix)
    assert update_fix_from_sentence(THS_INVALID, fix) == "THS"
    assert fix.yaw_deg is None


def test_known_but_unparsed_sentence_leaves_fix_untouched():
    fix = GnssFix()
    assert update_fix_from_sentence(KSXT_NO_HEADING, fix) == "KSXT"
    assert fix == GnssFix()


@pytest.mark.parametrize(
    "sentence",
    ["", "$", "not a sentence", "$GNGGA,062133.000,*00", "$GNTHS,123.45,A*19"],
)
def test_unusable_sentences_return_none_and_change_nothing(sentence):
    fix = GnssFix()
    assert update_fix_from_sentence(sentence, fix) is None
    assert fix == GnssFix()
