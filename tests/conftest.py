"""Fixture sentences captured from UM982 output shapes.

Every checksum here was verified before being committed, so a failure in
these tests points at the parser rather than at the fixture.
"""

GGA_RTK_FIXED = (
    "$GNGGA,062133.000,2503.7458570,N,12134.8712341,E,4,28,0.60,"
    "45.123,M,17.456,M,1.0,0000*66"
)
GGA_NO_FIX = "$GNGGA,062134.000,,,,,0,04,99.99,,M,,M,,*4E"
# NMEA 4.10 appends system_id, NMEA 2.3 does not; DOP offsets must match.
GSA_WITH_SYSTEM_ID = (
    "$GNGSA,A,3,03,09,17,19,22,23,31,32,,,,,1.20,0.70,0.98,1*02"
)
GSA_ALL_SLOTS_USED = (
    "$GNGSA,A,3,01,02,03,04,05,06,07,08,09,10,11,12,1.20,0.70,0.98,1*07"
)
GSA_WITHOUT_SYSTEM_ID = (
    "$GPGSA,A,3,03,09,17,19,22,23,31,32,,,,,1.20,0.70,0.98*01"
)
THS_VALID = "$GNTHS,123.45,A*18"
THS_INVALID = "$GNTHS,,V*10"

# Enabled on the module but deliberately not parsed yet.
RMC_SENTENCE = (
    "$GNRMC,062133.000,A,2503.7458570,N,12134.8712341,E,0.024,,"
    "220926,,,D,V*28"
)
VTG_SENTENCE = "$GNVTG,,T,,M,0.024,N,0.044,K,D*3E"
GST_SENTENCE = "$GNGST,062133.000,2.5,1.2,0.8,45.0,1.1,1.0,2.0*42"
GSV_SENTENCE = (
    "$GPGSV,3,1,11,03,60,180,45,09,45,090,42,17,30,270,40,"
    "19,20,045,38,1*68"
)
# Captured from a UM982 R4.10Build13495 indoors: single-point position
# and no heading, because ANT2 solved with no satellites. Field layout
# per Unicore N4 manual R1.15 Table 7-107; the fixture it replaces was
# invented and had every field after the heading in the wrong place.
KSXT_NO_HEADING = (
    "$KSXT,20261021094631.60,121.45666133,24.99834109,36.6279,0.00,"
    "0.00,199.17,0.918,0.00,1,0,0,15,,,,-0.301,-0.867,0.161,,*36"
)

UNPARSED_SENTENCES = [
    RMC_SENTENCE,
    VTG_SENTENCE,
    GST_SENTENCE,
    GSV_SENTENCE,
    KSXT_NO_HEADING,
]
