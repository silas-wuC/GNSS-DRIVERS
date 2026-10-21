import pytest

from gnss_drivers.um982.driver import (
    MODULE_INIT_COMMANDS,
    SAVECONFIG_COMMAND,
    UM982,
    InitTiming,
    UM982InitError,
    UM982ReadError,
    reply_status_text,
)

# Zero pacing keeps the init sequence from sleeping through the test run;
# the short reply timeout only bites in the missing-reply test.
NO_WAIT_TIMING = InitTiming(
    cmd_delay_s=0.0,
    saveconfig_settle_s=0.0,
    reply_timeout_s=0.05,
    drain_read_timeout_s=0.0,
)

THS_STREAM_LINE = b"$GNTHS,,V*10\r\n"
# Captured from a UM982 R4.10Build13495.
UNLOG_OK_REPLY = b"$command,UNLOG,response: OK*01\r\n"
UNLOGCOM_REJECTED_REPLY = (
    b"$command,UNLOGCOM,"
    b"response: PARSING FAILED NO MATCHING FUNC  UNLOGCOM*05\r\n"
)
MODE_REJECTED_REPLY = (
    b"$command,CONFIG MODE UAV,"
    b"response: PARSING FAILED MISSING FIELD,*48\r\n"
)


class FakeSerialPort:
    """Records writes and replays queued lines; b"" means a read timeout.

    auto_reply answers every write with an OK reply, as the module does
    for each command it accepts.
    """

    def __init__(self, queued_lines=None, auto_reply=False):
        self.timeout = 1.0
        self.written_commands = []
        self.queued_lines = list(queued_lines or [])
        self.auto_reply = auto_reply

    def write(self, payload):
        command_text = payload.decode("ascii").strip()
        self.written_commands.append(command_text)
        if self.auto_reply:
            reply_text = "$command," + command_text + ",response: OK*00\r\n"
            self.queued_lines.append(reply_text.encode("ascii"))

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
    fake_port = FakeSerialPort(auto_reply=True)
    receiver = make_receiver(fake_port)
    progress_lines = list(receiver.apply_init_commands())
    assert fake_port.written_commands == MODULE_INIT_COMMANDS
    assert len(progress_lines) == len(MODULE_INIT_COMMANDS)


def test_init_commands_override_replaces_default_list():
    fake_port = FakeSerialPort(auto_reply=True)
    receiver = make_receiver(fake_port)
    custom_commands = ["UNLOG", "CONFIG HEADING LENGTH 150"]
    list(receiver.apply_init_commands(init_commands=custom_commands))
    assert fake_port.written_commands == custom_commands


def test_save_to_flash_appends_saveconfig_last():
    fake_port = FakeSerialPort(auto_reply=True)
    receiver = make_receiver(fake_port)
    list(
        receiver.apply_init_commands(
            save_to_flash=True, init_commands=["UNLOG"]
        )
    )
    assert fake_port.written_commands == ["UNLOG", SAVECONFIG_COMMAND]


def test_reply_behind_streaming_nmea_is_found():
    # A backed-up module queues the reply behind far more than the three
    # lines the old drain window read, which hid every rejection.
    fake_port = FakeSerialPort([THS_STREAM_LINE] * 50 + [UNLOG_OK_REPLY])
    receiver = make_receiver(fake_port)
    progress_lines = list(
        receiver.apply_init_commands(init_commands=["UNLOG"])
    )
    assert progress_lines == ["1/1 UNLOG -> response: OK"]


def test_missing_reply_raises_init_error():
    receiver = make_receiver(FakeSerialPort([THS_STREAM_LINE]))
    with pytest.raises(UM982InitError, match="UNLOG: no reply"):
        list(receiver.apply_init_commands(init_commands=["UNLOG"]))


def test_rejected_command_raises_with_module_reason():
    fake_port = FakeSerialPort([THS_STREAM_LINE, UNLOGCOM_REJECTED_REPLY])
    receiver = make_receiver(fake_port)
    with pytest.raises(
        UM982InitError, match="UNLOGCOM: response: PARSING FAILED"
    ):
        list(receiver.apply_init_commands(init_commands=["UNLOGCOM"]))


def test_init_stops_at_first_rejected_command():
    fake_port = FakeSerialPort([UNLOG_OK_REPLY, MODE_REJECTED_REPLY])
    receiver = make_receiver(fake_port)
    init_commands = ["UNLOG", "CONFIG MODE UAV", "GPGGA 0.05"]
    progress_lines = []
    with pytest.raises(UM982InitError):
        for progress_text in receiver.apply_init_commands(
            init_commands=init_commands
        ):
            progress_lines.append(progress_text)
    assert progress_lines == ["1/3 UNLOG -> response: OK"]
    assert fake_port.written_commands == ["UNLOG", "CONFIG MODE UAV"]


def test_reply_status_text_strips_echo_and_checksum():
    reply_line = "$command,CONFIG HEADING LENGTH 150,response: OK*1A"
    assert reply_status_text(reply_line) == "response: OK"


def test_reply_status_text_keeps_commas_in_reason():
    reply_line = (
        "$command,CONFIG PPP TIMEOUT 300,"
        "response: PARSING FAILED FIELD OUT OF RANGE,300*7E"
    )
    assert reply_status_text(reply_line) == (
        "response: PARSING FAILED FIELD OUT OF RANGE,300"
    )


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
