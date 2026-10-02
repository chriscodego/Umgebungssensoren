import threading
import time

import pytest

from umwelt_ctl import cli
from umwelt_ctl.device import DeviceDisconnected, PortBusy, UmweltDevice

from conftest import FakeTransport, FakeUmwelt


@pytest.fixture
def env(monkeypatch):
    model = FakeUmwelt()
    transports: list[FakeTransport] = []
    opened: list[str | None] = []

    def open_device(port):
        opened.append(port)
        tr = FakeTransport(model)
        transports.append(tr)
        dev = UmweltDevice(tr, timeout=1.0)
        dev.port = port or "COM99"
        dev.start()
        dev.wait_ready(boot_wait=0.5)
        return dev

    monkeypatch.setattr(cli, "open_device", open_device)
    return {"model": model, "transports": transports, "opened": opened}


def run(argv, capsys):
    code = cli.main(argv)
    out, err = capsys.readouterr()
    assert "Traceback" not in out + err
    return code, out, err


def test_help_is_german(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "Aufruf:" in out and "Befehle" in out and "Messwerte" in out
    with pytest.raises(SystemExit):
        cli.main(["config", "--help"])
    assert "Schwellwerte" in capsys.readouterr().out


def test_unknown_command_german_error(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(["blubb"])
    assert ei.value.code == 2
    assert "ungültige Auswahl" in capsys.readouterr().err


def test_ping(env, capsys):
    code, out, _ = run(["--port", "COM9", "ping"], capsys)
    assert code == 0
    assert "Umgebungssensoren Firmware 0.1.0 an COM9" in out
    assert env["opened"] == ["COM9"]
    assert env["transports"][0].closed  # port always released


def test_status_and_read(env, capsys):
    env["model"].alarm, env["model"].unacked = 1, 1
    code, out, _ = run(["status"], capsys)
    assert code == 0
    assert "Sensor OK" in out and "10 s" in out
    assert "Temperatur zu hoch (nicht quittiert)" in out
    code, out, _ = run(["read"], capsys)
    assert code == 0
    for text in ("21,34 °C", "45,12 % rF", "1013,2 hPa", "85000 Ω (85,0 kΩ)", "3 s"):
        assert text in out


def test_read_sensor_missing(env, capsys):
    env["model"].sensor = "MISSING"
    code, _, err = run(["read"], capsys)
    assert code == 1
    assert "Sensor nicht verfügbar" in err and "ERR 5" in err


def test_config_list_get_set(env, capsys):
    code, out, _ = run(["config"], capsys)
    assert code == 0
    assert "INTERVAL" in out and "10 s" in out and "T_HI" in out and "aus" in out
    code, out, _ = run(["config", "t_hi", "28,5"], capsys)
    assert code == 0
    assert env["model"].cfg["T_HI"] == 2850
    assert "aus → 28,50 °C" in out
    code, out, _ = run(["config", "T_HI"], capsys)
    assert "28,50 °C" in out
    code, out, _ = run(["config", "T_HI", "OFF"], capsys)
    assert env["model"].cfg["T_HI"] is None


def test_config_invalid_value_is_rejected_before_connecting(env, capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(["config", "T_HI", "99"])
    assert ei.value.code == 2
    assert "außerhalb" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["config", "FOO", "1"])
    assert "Unbekannte Einstellung" in capsys.readouterr().err
    assert env["opened"] == []


def test_config_reset_needs_confirmation(env, capsys, monkeypatch):
    env["model"].cfg["INTERVAL"] = 60
    monkeypatch.setattr("builtins.input", lambda _q: "n")
    code, out, _ = run(["config", "reset"], capsys)
    assert code == 1 and "Abgebrochen" in out
    assert env["opened"] == []  # not even connected
    monkeypatch.setattr("builtins.input", lambda _q: "j")
    code, _, _ = run(["config", "reset"], capsys)
    assert code == 0 and env["model"].cfg["INTERVAL"] == 10
    env["model"].cfg["INTERVAL"] = 60
    code, _, _ = run(["config", "reset", "-y"], capsys)
    assert code == 0 and env["model"].cfg["INTERVAL"] == 10


def test_ack(env, capsys):
    code, _, err = run(["ack"], capsys)
    assert code == 1
    assert "kein unquittierter Alarm" in err
    env["model"].unacked = 1
    code, out, _ = run(["ack"], capsys)
    assert code == 0 and "quittiert" in out


def test_time_and_sync(env, capsys):
    code, out, _ = run(["time"], capsys)
    assert code == 0 and "nicht gestellt" in out
    code, out, _ = run(["time", "sync"], capsys)
    assert code == 0 and "Uhr am Gerät gestellt" in out
    assert env["model"].clock is not None
    code, out, _ = run(["time"], capsys)
    assert "Abweichung" in out


def test_connection_failures_are_one_german_line(monkeypatch, capsys):
    def fail(port):
        raise DeviceDisconnected("Kein Arduino (USB-VID 0x2341) gefunden.")

    monkeypatch.setattr(cli, "open_device", fail)
    code, _, err = run(["status"], capsys)
    assert code == 2
    assert "Verbindung fehlgeschlagen: Kein Arduino" in err

    def busy(port):
        raise PortBusy("Port COM9 ist belegt – bitte schließen.")

    monkeypatch.setattr(cli, "open_device", busy)
    code, _, err = run(["read"], capsys)
    assert code == 2 and "belegt" in err


def test_ports(monkeypatch, capsys):
    monkeypatch.setattr(cli, "list_all_ports",
                        lambda: [("COM1", "Kommunikationsanschluss", False),
                                 ("COM9", "Arduino Uno", True)])
    code, out, _ = run(["ports"], capsys)
    assert code == 0
    assert "COM9" in out and "← Arduino" in out


def _run_monitor(argv, stop_when, monkeypatch, timeout=8.0):
    state = {"stop": False}
    monkeypatch.setattr(cli, "monitor_should_stop", lambda: state["stop"])
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("code", cli.main(argv)))
    t.start()
    end = time.monotonic() + timeout
    try:
        while time.monotonic() < end and not stop_when():
            time.sleep(0.02)
    finally:
        state["stop"] = True
        t.join(5)
    return result.get("code")


def test_monitor_stream_writes_csv(env, monkeypatch, capsys, tmp_path):
    model = env["model"]
    csv = tmp_path / "messwerte.csv"

    def driver():
        if not model.stream:
            return False
        if not getattr(driver, "done", False):
            driver.done = True
            model.measure((2150, 4600, 10140, 90000))
            env["transports"][0].send("EVT DATA kaputt - - -")  # skipped, no row
            model.raise_alarm(1)
            time.sleep(0.1)
            model.set_sensor("MISSING")
            model.measure()
        return csv.exists() and len(csv.read_text(encoding="utf-8-sig").splitlines()) >= 3

    code = _run_monitor(["monitor", "--csv", str(csv)], driver, monkeypatch)
    out, err = capsys.readouterr()
    assert code == 0
    lines = csv.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm"
    assert lines[1].split(";")[1:] == ["21,50", "46,00", "1014,0", "90000", "0"]
    assert lines[2].split(";")[1:] == ["", "", "", "", "17"]
    assert len(lines) == 3
    assert f"Messprotokoll: {csv}" in out
    assert "Alarm aktiv: Temperatur zu hoch" in out
    assert "Sensor nicht erreichbar" in out
    tr = env["transports"][0]
    assert "STREAM 1" in tr.written and tr.written[-1] == "STREAM 0"
    assert tr.closed
    assert "Traceback" not in out + err


def test_monitor_polling_with_missing_sensor(env, monkeypatch, capsys, tmp_path):
    env["model"].sensor = "MISSING"
    csv = tmp_path / "poll.csv"

    def done():
        return csv.exists() and len(csv.read_text(encoding="utf-8-sig").splitlines()) >= 2

    code = _run_monitor(["monitor", "--interval", "1", "--csv", str(csv)], done, monkeypatch)
    capsys.readouterr()
    assert code == 0
    lines = csv.read_text(encoding="utf-8-sig").splitlines()
    assert lines[1].split(";")[1:] == ["", "", "", "", "16"]
    assert "STREAM 1" not in env["transports"][0].written
