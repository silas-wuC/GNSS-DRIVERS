import pytest

from gnss_drivers.um982.driver import (
    MODULE_INIT_COMMANDS,
    SAVECONFIG_COMMAND,
    UM982,
    InitTiming,
    UM982ReadError,
    reply_status_text,
)

# Zero pacing keeps the init sequence from sleeping through the test run.
NO_WAIT_TIMING = InitTiming(
    cmd_delay_s=0.0,
    saveconfig_settle_s=0.0,
    drain_lines_max=3,
    drain_read_timeout_s=0.0,
)


class FakeSerialPort:
    """Records writes and replays queued lines; b"" means a read timeout."""

    def __init__(self, queued_lines=None):
        self.timeout = 1.0
        self.written_commands = []
        self.queued_lines = list(queued_lines or [])

    def write(self, payload):
        self.written_commands.append(payload.decode("ascii").strip())

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def readline(self):
        if not self.queued_lines:
            return b""
        return self.queued_lines.pop(0)

    def close(self):
        pass


def make_receiver(fake_port, empty_read_limit=3):
    receiver = UM982(
        "COM29",
        empty_read_limit=empty_read_limit,
        init_timing=NO_WAIT_TIMING,
    )
    receiver._serial = fake_port
    return receiver


def test_default_init_sends_module_commands_in_order():
    fake_port = FakeSerialPort()
    receiver = make_receiver(fake_port)
    progress_lines = list(receiver.apply_init_commands())
    assert fake_port.written_commands == MODULE_INIT_COMMANDS
    assert len(progress_lines) == len(MODULE_INIT_COMMANDS)


def test_init_commands_override_replaces_default_list():
    fake_port = FakeSerialPort()
    receiver = make_receiver(fake_port)
    custom_commands = ["UNLOG", "CONFIG HEADING LENGTH 150"]
    list(receiver.apply_init_commands(init_commands=custom_commands))
    assert fake_port.written_commands == custom_commands


def test_save_to_flash_appends_saveconfig_last():
    fake_port = FakeSerialPort()
    receiver = make_receiver(fake_port)
    list(
        receiver.apply_init_commands(
            save_to_flash=True, init_commands=["UNLOG"]
        )
    )
    assert fake_port.written_commands == ["UNLOG", SAVECONFIG_COMMAND]


def test_progress_line_reports_module_reply():
    # The reply can sit behind streaming NMEA inside the drain window.
    fake_port = FakeSerialPort(
        [
            b"$GNTHS,,V*10\r\n",
            b"$command,UNLOG,response: OK*01\r\n",
        ]
    )
    receiver = make_receiver(fake_port)
    progress_lines = list(
        receiver.apply_init_commands(init_commands=["UNLOG"])
    )
    assert progress_lines == ["1/1 UNLOG -> response: OK"]


def test_progress_line_flags_missing_reply():
    fake_port = FakeSerialPort([b"$GNTHS,,V*10\r\n"])
    receiver = make_receiver(fake_port)
    progress_lines = list(
        receiver.apply_init_commands(init_commands=["UNLOG"])
    )
    assert progress_lines == ["1/1 UNLOG -> no response seen"]


def test_reply_status_text_strips_echo_and_checksum():
    reply_line = "$command,CONFIG HEADING LENGTH 150,response: OK*1A"
    assert reply_status_text(reply_line) == "response: OK"


def test_read_fixes_raises_after_empty_read_limit():
    receiver = make_receiver(FakeSerialPort(), empty_read_limit=3)
    with pytest.raises(UM982ReadError):
        next(receiver.read_fixes())


def test_zero_empty_read_limit_keeps_waiting():
    # Ten timeouts would trip any non-zero limit used in these tests.
    queued_lines = [b""] * 10 + [b"$GNTHS,123.45,A*18\r\n"]
    receiver = make_receiver(
        FakeSerialPort(queued_lines), empty_read_limit=0
    )
    fix = next(receiver.read_fixes())
    assert fix.yaw_deg == pytest.approx(123.45)
