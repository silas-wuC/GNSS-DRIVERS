from pathlib import Path

import pytest

from gnss_drivers.um982 import __main__ as um982_cli
from gnss_drivers.um982.config import (
    DEFAULT_CONFIG_PATH,
    UM982Config,
    UM982ConfigError,
    load_config_file,
    validate_config,
)
from gnss_drivers.um982.driver import UM982ReadError

EXAMPLE_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "gnss_drivers"
    / "um982"
    / "um982.example.toml"
)


def write_config(tmp_path, toml_text):
    config_path = tmp_path / "bench.toml"
    config_path.write_text(toml_text)
    return str(config_path)


def build_from_argv(argv):
    return um982_cli.build_config(um982_cli.parse_args(argv))


def test_missing_default_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config, config_note = load_config_file(None)
    assert config == UM982Config()
    assert config_note == DEFAULT_CONFIG_PATH + " not found, using defaults"


def test_default_file_in_working_directory_is_loaded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / DEFAULT_CONFIG_PATH).write_text('[serial]\nport = "COM29"\n')
    config, config_note = load_config_file(None)
    assert config.port == "COM29"
    assert config_note == DEFAULT_CONFIG_PATH


def test_explicit_missing_file_is_an_error(tmp_path):
    with pytest.raises(UM982ConfigError, match="file not found"):
        load_config_file(str(tmp_path / "nope.toml"))


def test_example_file_matches_code_defaults():
    # The template documents the defaults; drift would mislead operators.
    config, _ = load_config_file(str(EXAMPLE_CONFIG_PATH))
    assert config == UM982Config()


@pytest.mark.parametrize(
    "toml_text, error_text",
    [
        ("[serial]\nbuad = 115200\n", "serial.buad: unknown key"),
        ("[serail]\nbaud = 115200\n", r"unknown section \[serail\]"),
        ("[serial]\nbaud = true\n", "serial.baud: expected int, got bool"),
        ('[serial]\nbaud = "fast"\n', "serial.baud: expected int, got str"),
        ("[run]\ndump = 1\n", "run.dump: expected bool, got int"),
        ("[init]\ncommands = [1]\n", "every entry must be a string"),
        ("serial = 1\n", "expected a \\[serial\\] table"),
        ("[serial\n", "bench.toml"),
    ],
)
def test_bad_config_names_the_offending_key(tmp_path, toml_text, error_text):
    config_path = write_config(tmp_path, toml_text)
    with pytest.raises(UM982ConfigError, match=error_text):
        load_config_file(config_path)


def test_float_fields_accept_toml_integers(tmp_path):
    config_path = write_config(tmp_path, "[serial]\nread_timeout_s = 2\n")
    config, _ = load_config_file(config_path)
    assert config.read_timeout_s == pytest.approx(2.0)
    assert isinstance(config.read_timeout_s, float)


def test_init_commands_replace_default_list(tmp_path):
    config_path = write_config(
        tmp_path,
        '[init]\ncommands = ["UNLOG", "CONFIG HEADING LENGTH 150"]\n',
    )
    config, _ = load_config_file(config_path)
    assert config.init_commands == ["UNLOG", "CONFIG HEADING LENGTH 150"]


@pytest.mark.parametrize(
    "command_list, error_text",
    [
        (["UNLOG", "SAVECONFIG"], "must not contain SAVECONFIG"),
        (["UNLOG", " saveconfig "], "must not contain SAVECONFIG"),
        (["UNLOG", "  "], "blank entry"),
        ([], "must not be empty"),
    ],
)
def test_bad_init_commands_are_rejected(command_list, error_text):
    config = UM982Config(init_commands=command_list)
    with pytest.raises(UM982ConfigError, match=error_text):
        validate_config(config)


@pytest.mark.parametrize(
    "field_name, bad_value",
    [
        ("baud", 0),
        ("read_timeout_s", 0.0),
        ("init_drain_read_timeout_s", 0.0),
        ("empty_read_limit", -1),
        ("init_cmd_delay_s", -0.1),
    ],
)
def test_out_of_range_values_are_rejected(field_name, bad_value):
    config = UM982Config()
    setattr(config, field_name, bad_value)
    with pytest.raises(UM982ConfigError, match=field_name):
        validate_config(config)


def test_flags_override_file_values(tmp_path):
    config_path = write_config(
        tmp_path,
        '[serial]\nport = "COM29"\nbaud = 230400\n'
        "[run]\ndump = true\ninit = true\n",
    )
    config, _ = build_from_argv(
        ["--config", config_path, "--baud", "115200", "--no-dump",
         "--no-init"]
    )
    assert config.baud == 115200
    assert config.dump is False
    assert config.init is False
    # A flag that was not passed must leave the file value alone.
    assert config.port == "COM29"


def test_flag_values_go_through_range_checks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(UM982ConfigError, match="baud"):
        build_from_argv(["--baud", "0"])


def test_cli_reports_config_error_and_exits_nonzero(tmp_path, capsys):
    config_path = write_config(tmp_path, "[serial]\nbuad = 1\n")
    assert um982_cli.main(["--config", config_path]) == 1
    assert "serial.buad: unknown key" in capsys.readouterr().out


class SilentReceiver:
    """Stands in for UM982 when only read_sentence() timeouts matter."""

    def __init__(self):
        self.fix = None
        self.read_count = 0

    def read_sentence(self):
        self.read_count += 1
        return None


def test_read_loop_exits_after_empty_read_limit():
    receiver = SilentReceiver()
    config = UM982Config(empty_read_limit=3, no_data_warn_after_s=60.0)
    with pytest.raises(UM982ReadError):
        um982_cli.run_read_loop(receiver, config)
    assert receiver.read_count == 3
