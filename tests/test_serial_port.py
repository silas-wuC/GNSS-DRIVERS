import sys

from gnss_drivers import serial_port


def test_posix_paths_are_untouched(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert serial_port.resolve_port_path("/dev/ttyUSB0") == "/dev/ttyUSB0"
    # A udev rule may name a Linux device COM29; it must not be rewritten.
    assert serial_port.resolve_port_path("COM29") == "COM29"


def test_windows_expands_only_com10_and_above(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert serial_port.resolve_port_path("COM5") == "COM5"
    assert serial_port.resolve_port_path("COM9") == "COM9"
    assert serial_port.resolve_port_path("COM10") == r"\\.\COM10"
    assert serial_port.resolve_port_path("COM29") == r"\\.\COM29"


def test_windows_ignores_non_numeric_port_names(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert serial_port.resolve_port_path("COMx") == "COMx"
    assert serial_port.resolve_port_path("ttyS0") == "ttyS0"
