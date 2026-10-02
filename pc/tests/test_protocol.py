import datetime as dt

import pytest

from umwelt_ctl import protocol as p
from umwelt_ctl.protocol import DeviceError, DeviceStatus, Event, Measurement, ProtocolError

# --------------------------------------------------------------------------- conversion


@pytest.mark.parametrize("raw,decimals,text", [
    (2134, 2, "21,34"), (-5, 2, "-0,05"), (-4000, 2, "-40,00"), (8500, 2, "85,00"),
    (0, 2, "0,00"), (10132, 1, "1013,2"), (3000, 1, "300,0"), (7, 0, "7"),
])
def test_format_scaled_is_exact(raw, decimals, text):
    assert p.format_scaled(raw, decimals) == text


def test_unit_formatting():
    assert p.format_temperature(2134) == "21,34 °C"
    assert p.format_temperature(-1234) == "-12,34 °C"
    assert p.format_temperature(None) == "--"
    assert p.format_humidity(4512) == "45,12 % rF"
    assert p.format_pressure(10132) == "1013,2 hPa"
    assert p.format_gas(85000) == "85,0 kΩ"
    assert p.format_gas(85049) == "85,0 kΩ"
    assert p.format_gas(85050) == "85,1 kΩ"
    assert p.format_gas(85000, kilo=False) == "85000 Ω"
    assert p.format_gas(None) == "--"


def test_measurement_physical_units():
    m = Measurement(t=-4000, rh=10000, p=11000, gas=1)
    assert m.temperature_c == -40.0
    assert m.humidity_pct == 100.0
    assert m.pressure_hpa == 1100.0
    assert m.gas_ohm == 1
    assert Measurement().temperature_c is None
    assert not Measurement().any_valid


def test_csv_fields_invalid_empty_never_zero():
    assert Measurement(2134, 4512, 10132, 85000).csv_fields() == (
        "21,34", "45,12", "1013,2", "85000")
    assert Measurement(None, 0, None, None).csv_fields() == ("", "0,00", "", "")


def test_parse_values_dash_and_boundaries():
    m = p.parse_values(["-4000", "0", "3000", "1"])
    assert (m.t, m.rh, m.p, m.gas) == (-4000, 0, 3000, 1)
    m = p.parse_values(["8500", "10000", "11000", "4294967295"])
    assert (m.t, m.rh, m.p, m.gas) == (8500, 10000, 11000, 4294967295)
    assert p.parse_values(["-", "-", "-", "-"]) == Measurement()


def test_parse_values_out_of_plausibility_becomes_invalid():
    m = p.parse_values(["8501", "10001", "2999", "0"])
    assert m == Measurement()  # never shown/logged as real numbers


@pytest.mark.parametrize("tokens", [
    ["21.3", "4512", "10132", "85000"], ["abc", "-", "-", "-"], ["1", "2", "3"],
    ["1", "2", "3", "4", "5"], ["--", "1", "1", "1"],
])
def test_parse_values_garbage_raises(tokens):
    with pytest.raises(ProtocolError):
        p.parse_values(tokens)


def test_parse_read():
    m = p.parse_read(("2134", "4512", "10132", "85000", "3"))
    assert m == Measurement(2134, 4512, 10132, 85000, 3)
    assert p.parse_read(("-", "-", "-", "-", "-")).age_sec is None
    with pytest.raises(ProtocolError):
        p.parse_read(("2134", "4512", "10132", "85000"))


# --------------------------------------------------------------------------- status / alarm


def test_parse_status():
    st = p.parse_status(("OK", "10", "3600", "5", "1"))
    assert st == DeviceStatus("OK", 10, 3600, 5, 1)
    assert st.alarm_active and st.needs_ack
    assert st.sensor_text == "Sensor OK"
    assert p.parse_status(("missing", "10", "0", "16", "16")).sensor_text == \
        "Sensor nicht erreichbar"


@pytest.mark.parametrize("args", [
    ("OK", "10", "1"), ("FOO", "10", "1", "0", "0"), ("OK", "x", "1", "0", "0"),
    ("OK", "10", "1", "32", "0"), ("OK", "0", "1", "0", "0"),
])
def test_parse_status_rejects_bad_shapes(args):
    with pytest.raises(ProtocolError):
        p.parse_status(args)


def test_alarm_texts():
    assert p.alarm_texts(0) == []
    assert p.alarm_texts(1 | 8 | 16) == ["Temperatur zu hoch", "Luftfeuchte zu niedrig",
                                         "keine Messdaten (Sensor fehlt oder Messfehler)"]


# --------------------------------------------------------------------------- errors


@pytest.mark.parametrize("code,needle", [
    (1, "kennt diesen Befehl nicht"), (2, "falsches Format"), (3, "außerhalb des erlaubten"),
    (5, "Sensor nicht verfügbar"), (7, "aktuellen Zustand"),
])
def test_every_spec_error_code_has_a_german_text(code, needle):
    err = p.parse_err(f"ERR {code} whatever")
    assert isinstance(err, DeviceError)
    assert err.code == code
    assert needle in str(err)
    assert f"ERR {code}" in str(err)


def test_error_table_covers_exactly_the_spec_codes():
    assert set(p.ERROR_TEXTS_DE) == {1, 2, 3, 5, 7}


def test_unknown_error_code_fallback():
    assert "Code 9" in str(p.parse_err("ERR 9 x"))
    assert p.parse_err("ERR").code == -1


# --------------------------------------------------------------------------- events


def test_parse_events():
    assert p.parse_event("EVT DATA 2134 - 10132 85000").measurement == Measurement(
        2134, None, 10132, 85000)
    assert p.parse_event("EVT ALARM 4 1") == Event("ALARM", flag=4, active=True)
    assert p.parse_event("evt alarm 16 0") == Event("ALARM", flag=16, active=False)
    assert p.parse_event("EVT SENSOR MISSING") == Event("SENSOR", sensor="MISSING")
    assert p.parse_event("EVT BOOT 0.1.0").fw_version == "0.1.0"
    assert p.parse_event("EVT FUTURE 1 2").kind == "FUTURE"


@pytest.mark.parametrize("line", [
    "EVT DATA 2134 4512 10132", "EVT DATA x y z w", "EVT DATA 1 2 3 4 5",
    "EVT ALARM 3 1", "EVT ALARM 1 2", "EVT ALARM 1", "EVT SENSOR BROKEN", "EVT",
])
def test_malformed_events_raise(line):
    with pytest.raises(ProtocolError):
        p.parse_event(line)


# --------------------------------------------------------------------------- config


@pytest.mark.parametrize("key,text,wire", [
    ("T_HI", "28,5", "2850"), ("t_hi", "28.5", "2850"), ("T_LO", "-40", "-4000"),
    ("T_HI", "OFF", "OFF"), ("RH_LO", "aus", "OFF"), ("RH_HI", "", "OFF"),
    ("RH_HI", "100", "10000"), ("TEMP_OFFSET", "-1,25", "-125"), ("INTERVAL", "3600", "3600"),
    ("BUZZER", "an", "1"), ("BUZZER", "0", "0"), ("BUZZER", "aus", "0"),
])
def test_parse_config_input(key, text, wire):
    assert p.parse_config_input(key, text) == wire


@pytest.mark.parametrize("key,text,needle", [
    ("T_HI", "85,01", "außerhalb"), ("T_HI", "28,555", "Nachkommastellen"),
    ("INTERVAL", "0", "außerhalb"), ("INTERVAL", "1,5", "ganze Sekunden"),
    ("INTERVAL", "OFF", "keine Zahl"), ("TEMP_OFFSET", "OFF", "keine Zahl"),
    ("BUZZER", "2", "0/1"), ("FOO", "1", "Unbekannte Einstellung"), ("RH_HI", "abc", "keine Zahl"),
    ("T_HI", "nan", "keine Zahl"),
])
def test_parse_config_input_rejects(key, text, needle):
    with pytest.raises(ValueError, match=needle):
        p.parse_config_input(key, text)


def test_parse_config_list_and_format():
    cfg = p.parse_config(["C INTERVAL 10", "C T_HI 2850", "C RH_LO OFF", "C NEWKEY 5"])
    assert cfg == {"INTERVAL": 10, "T_HI": 2850, "RH_LO": None}
    assert p.format_config_value("T_HI", 2850) == "28,50 °C"
    assert p.format_config_value("RH_LO", None) == "aus"
    assert p.format_config_value("INTERVAL", 10) == "10 s"
    assert p.format_config_value("BUZZER", 1) == "an"
    assert p.config_input_text("T_HI", 2850) == "28,5"
    assert p.config_input_text("T_HI", 2800) == "28"
    assert p.config_input_text("TEMP_OFFSET", -5) == "-0,05"
    assert p.config_input_text("T_LO", None) == "OFF"
    with pytest.raises(ProtocolError):
        p.parse_config_line("C T_HI")


# --------------------------------------------------------------------------- commands & misc


def test_command_builders():
    assert p.cmd_ping() == "PING"
    assert p.cmd_status() == "STATUS"
    assert p.cmd_read() == "READ"
    assert p.cmd_cfg_list() == "CFG"
    assert p.cmd_cfg_set("t_hi", "2850") == "CFG T_HI 2850"
    assert p.cmd_cfg_set("T_LO", "off") == "CFG T_LO OFF"
    assert p.cmd_cfg_reset() == "CFG RESET"
    assert p.cmd_stream(True) == "STREAM 1"
    assert p.cmd_ack() == "ACK"
    assert p.cmd_time_get() == "TIME"
    assert p.cmd_time_set(dt.time(7, 5, 9)) == "TIME 07:05:09"
    with pytest.raises(ValueError):
        p.cmd_cfg_set("INTERVAL", "OFF")
    with pytest.raises(ValueError):
        p.cmd_cfg_set("INTERVAL", "0")


def test_command_too_long_rejected():
    with pytest.raises(ValueError, match="zu lang"):
        p._cmd("X" * 81)
    assert p._cmd("X" * 80)


def test_pong_and_versions():
    assert p.parse_pong(("PONG", "Umgebungssensoren", "0.1.0")) == "0.1.0"
    with pytest.raises(ProtocolError, match="GloveboxControl"):
        p.parse_pong(("PONG", "GloveboxControl", "0.4.0"))
    assert p.version_older("0.0.9", "0.1.0")
    assert not p.version_older("0.1.0", "0.1.0")
    assert not p.version_older(None, "0.1.0")


def test_clock_helpers():
    assert p.parse_time_reply(("--:--:--",)) is None
    assert p.parse_time_reply(("23:59:58",)) == dt.time(23, 59, 58)
    with pytest.raises(ProtocolError):
        p.parse_clock("24:00:00")
    assert p.clock_difference_sec(dt.time(0, 0, 5), dt.time(23, 59, 55)) == 10
    assert p.format_uptime(90061) == "1 d 01:01:01"


def test_line_classification():
    assert p.is_event_line("evt DATA 1 2 3 4")
    assert p.is_ok_line("OK")
    assert p.is_end_line(" end ")
    assert p.clean_line(b"OK PONG\r") == "OK PONG"
    assert p.clean_line(b"\xff\xfeOK").endswith("OK")
