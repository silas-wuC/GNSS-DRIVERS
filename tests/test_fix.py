import pytest

from gnss_drivers.fix import GnssFix, format_fix_line, format_optional_number


def test_empty_fix_formats_placeholders():
    line = format_fix_line(GnssFix())
    assert "LAT --" in line
    assert "SATS --" in line
    assert "YAW --" in line
    assert "RTK --" in line
    assert "HDG --" in line
    assert "ANT2 --" in line


def test_status_line_shows_rtk_and_heading_state():
    fix = GnssFix(
        position_quality=4, yaw_deg=299.22, heading_quality=3,
        ant2_sats_used=46,
    )
    line = format_fix_line(fix)
    assert "RTK FIXED" in line
    assert "YAW 299.2  HDG FIXED  ANT2 46" in line


@pytest.mark.parametrize(
    "position_quality, heading_quality, expected_texts",
    [
        (5, 2, ["RTK FLOAT", "HDG FLOAT"]),
        (0, 0, ["RTK NONE", "HDG NONE"]),
        (1, 1, ["RTK SINGLE", "HDG SINGLE"]),
        # GGA 4 is fixed, but KSXT has no 4; the two tables must not mix.
        (4, 4, ["RTK FIXED", "HDG Q4"]),
    ],
)
def test_quality_tables_follow_their_own_numbering(
    position_quality, heading_quality, expected_texts
):
    fix = GnssFix(
        position_quality=position_quality, heading_quality=heading_quality
    )
    line = format_fix_line(fix)
    for expected_text in expected_texts:
        assert expected_text in line


def test_format_optional_number_rounds_and_placeholders():
    assert format_optional_number(None, 1) == "--"
    assert format_optional_number(1.25, 1) == "1.2"
    assert format_optional_number(24.998472, 6) == "24.998472"


def test_clear_position_keeps_time_and_satellites():
    fix = GnssFix(
        utc_text="06:21:33.000",
        lat_deg=25.0,
        lon_deg=121.0,
        alt_msl_m=45.0,
        alt_hae_m=62.0,
        sats_used=28,
        hdop=0.6,
    )
    fix.clear_position()
    assert fix.lat_deg is None
    assert fix.lon_deg is None
    assert fix.alt_msl_m is None
    assert fix.alt_hae_m is None
    assert fix.utc_text == "06:21:33.000"
    assert fix.sats_used == 28
    assert fix.hdop == pytest.approx(0.6)
