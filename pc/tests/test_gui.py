"""GUI tests against the fake device (skipped if Tk cannot start)."""

import time

import pytest

from umwelt_ctl.device import UmweltDevice
from umwelt_ctl.protocol import DeviceError

from conftest import FakeTransport, FakeUmwelt

tk = pytest.importorskip("tkinter")


@pytest.fixture(scope="module")
def tk_root():
    last = None
    for _ in range(3):
        try:
            root = tk.Tk()
            break
        except tk.TclError as exc:  # pragma: no cover - headless machine
            last = exc
            time.sleep(0.2)
    else:  # pragma: no cover
        pytest.skip(f"Tk nicht verfügbar: {last}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def gui_env(tk_root, tmp_path, monkeypatch):
    from umwelt_ctl import gui

    root = tk.Toplevel(tk_root)
    root.withdraw()
    dialogs = []
    for fn in ("showerror", "showwarning", "showinfo"):
        monkeypatch.setattr(gui.messagebox, fn,
                            lambda title, msg, _fn=fn, **kw: dialogs.append((_fn, title, msg)))
    confirm = {"answer": True, "asked": []}

    def askyesno(title, msg, **kw):
        confirm["asked"].append(title)
        return confirm["answer"]

    monkeypatch.setattr(gui.messagebox, "askyesno", askyesno)
    monkeypatch.setattr(root, "bell", lambda: None)
    monkeypatch.setattr(gui, "RETRY_AFTER_FAIL_S", 0.1)

    model = FakeUmwelt()
    transports = []
    plugged = {"on": True}

    def scan():
        return ["COM99"] if plugged["on"] else []

    def open_device(port):
        tr = FakeTransport(model)
        transports.append(tr)
        dev = UmweltDevice(tr, timeout=1.0)
        dev.port = port
        dev.start()
        dev.wait_ready(boot_wait=0.5)
        return dev

    csv_path = tmp_path / "umwelt_messwerte.csv"
    app = gui.App(root, open_device=open_device, scan_ports=scan, csv_path=str(csv_path))

    def pump(until, timeout=6.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            root.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    env = dict(app=app, root=root, model=model, transports=transports, plugged=plugged,
               pump=pump, dialogs=dialogs, csv=csv_path, confirm=confirm)
    yield env
    if not app._closing:
        app.on_close()


def connected_with_values(app):
    return app.connected and app.view_state() == "werte"


def test_connects_and_shows_four_tiles(gui_env):
    app, pump, model = gui_env["app"], gui_env["pump"], gui_env["model"]
    assert pump(lambda: connected_with_values(app))
    assert app.tiles["t"].value.cget("text") == "21,34 °C"
    assert app.tiles["rh"].value.cget("text") == "45,12 % rF"
    assert app.tiles["p"].value.cget("text") == "1013,2 hPa"
    assert app.tiles["gas"].value.cget("text") == "85,0 kΩ"
    assert "Sensor OK" in app.statusbar.cget("text")
    assert model.stream and model.clock is not None  # STREAM 1 + TIME after connect
    assert app.setting_vars["INTERVAL"].get() == "10"
    assert app.setting_vars["T_HI"].get() == ""


def test_live_data_updates_tiles_and_chart(gui_env):
    app, pump, model = gui_env["app"], gui_env["pump"], gui_env["model"]
    assert pump(lambda: connected_with_values(app))
    for t in (2000, 2050, 2100):
        model.measure((t, 5000, 10000, 70000))
    assert pump(lambda: len(app.chart) == 3)
    assert app.tiles["t"].value.cget("text") == "21,00 °C"
    assert app.canvas.find_all()  # line + labels drawn
    gui_env["transports"][-1].send("EVT DATA x y z w")  # garbage: ignored
    model.measure((-500, 5000, 10000, 70000))
    assert pump(lambda: len(app.chart) == 4)
    assert app.tiles["t"].value.cget("text") == "-5,00 °C"


def test_sensor_missing_state(gui_env):
    app, pump, model = gui_env["app"], gui_env["pump"], gui_env["model"]
    assert pump(lambda: connected_with_values(app))
    model.set_sensor("MISSING")
    model.measure()
    assert pump(lambda: app.view_state() == "sensorfehler")
    assert app.tiles["t"].value.cget("text") == "--"
    assert app.tiles["t"].sub.cget("text") == "Sensor nicht erreichbar"
    assert pump(lambda: app.alarm_frame.winfo_manager() == "pack")
    assert "keine Messdaten" in app.alarm_lbl.cget("text")


def test_sensor_missing_from_start(gui_env):
    gui_env["model"].sensor = "MISSING"
    app, pump = gui_env["app"], gui_env["pump"]
    assert pump(lambda: app.connected and app.view_state() == "sensorfehler")
    assert app.tiles["gas"].value.cget("text") == "--"


def test_alarm_banner_and_ack(gui_env):
    app, pump, model = gui_env["app"], gui_env["pump"], gui_env["model"]
    assert pump(lambda: connected_with_values(app))
    model.raise_alarm(1)
    assert pump(lambda: app.alarm_frame.winfo_manager() == "pack")
    assert "Temperatur zu hoch" in app.alarm_lbl.cget("text")
    assert "nicht quittiert" in app.alarm_lbl.cget("text")
    app.acknowledge()
    assert pump(lambda: model.unacked == 0 and "(quittiert)" in app.alarm_lbl.cget("text"))
    assert app.ack_btn.instate(["disabled"])
    model.alarm = 0
    model.emit("EVT ALARM 1 0")
    assert pump(lambda: app.alarm_frame.winfo_manager() == "")


def test_ack_error_is_german_dialog(gui_env):
    app, pump, dialogs = gui_env["app"], gui_env["pump"], gui_env["dialogs"]
    assert pump(lambda: connected_with_values(app))
    app.acknowledge()  # nothing to acknowledge -> ERR 7
    assert pump(lambda: dialogs and dialogs[-1][0] == "showerror")
    assert "kein unquittierter Alarm" in dialogs[-1][2]


def test_settings_apply_validate_and_reset(gui_env):
    app, pump, model = gui_env["app"], gui_env["pump"], gui_env["model"]
    dialogs, confirm = gui_env["dialogs"], gui_env["confirm"]
    assert pump(lambda: connected_with_values(app))
    app.setting_vars["T_HI"].set("90")
    app.apply_settings()
    assert dialogs[-1][0] == "showerror" and "außerhalb" in dialogs[-1][2]
    app.setting_vars["T_HI"].set("28,5")
    app.setting_vars["INTERVAL"].set("30")
    app.setting_vars["TEMP_OFFSET"].set("-1,5")
    app.buzzer_var.set(True)
    sent_before = len(gui_env["transports"][-1].written)
    app.apply_settings()
    assert pump(lambda: model.cfg["T_HI"] == 2850 and model.cfg["BUZZER"] == 1)
    assert model.cfg["INTERVAL"] == 30 and model.cfg["TEMP_OFFSET"] == -150
    sets = [c for c in gui_env["transports"][-1].written[sent_before:] if c.startswith("CFG ")]
    assert sorted(sets) == ["CFG BUZZER 1", "CFG INTERVAL 30", "CFG TEMP_OFFSET -150",
                            "CFG T_HI 2850"]  # only changed keys
    assert pump(lambda: app.config.get("T_HI") == 2850)

    confirm["answer"] = False
    app.reset_config()
    pump(lambda: False, timeout=0.2)
    assert model.cfg["T_HI"] == 2850  # declined -> nothing sent
    confirm["answer"] = True
    app.reset_config()
    assert pump(lambda: model.cfg["T_HI"] is None and app.setting_vars["T_HI"].get() == "")
    assert confirm["asked"] == ["Standardwerte", "Standardwerte"]


def test_csv_recording_toggle(gui_env):
    app, pump, model = gui_env["app"], gui_env["pump"], gui_env["model"]
    assert pump(lambda: connected_with_values(app))
    model.measure((2000, 5000, 10000, 1000))
    assert pump(lambda: len(app.chart) == 1)
    assert not gui_env["csv"].exists()  # off by default
    app.csv_on.set(True)
    app.toggle_csv()
    model.measure((2100, 5100, 10010, 1100))
    model.measure(("-", 5100, 10010, 1100))
    assert pump(lambda: app.logger is not None and app.logger.rows_written == 2)
    lines = gui_env["csv"].read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "zeit;temperatur_c;feuchte_proz;druck_hpa;gas_ohm;alarm"
    assert lines[1].split(";")[1:] == ["21,00", "51,00", "1001,0", "1100", "0"]
    assert lines[2].split(";")[1] == ""
    assert str(gui_env["csv"]) in app.csv_state.cget("text")
    app.csv_on.set(False)
    app.toggle_csv()
    model.measure((2200, 5100, 10010, 1100))
    assert pump(lambda: len(app.chart) == 4)
    assert len(gui_env["csv"].read_text(encoding="utf-8-sig").splitlines()) == 3


def test_reboot_mid_session_restores_stream(gui_env):
    app, pump, model = gui_env["app"], gui_env["pump"], gui_env["model"]
    assert pump(lambda: connected_with_values(app))
    model.reboot()
    assert pump(lambda: model.stream and model.clock is not None)
    assert pump(lambda: "neu gestartet" in app.message.cget("text"))
    model.measure((2300, 5000, 10000, 1000))
    assert pump(lambda: app.tiles["t"].value.cget("text") == "23,00 °C")


def test_disconnect_and_reconnect(gui_env):
    app, pump = gui_env["app"], gui_env["pump"]
    assert pump(lambda: connected_with_values(app))
    gui_env["plugged"]["on"] = False
    gui_env["transports"][-1].fail()
    assert pump(lambda: app.conn_state == "getrennt")
    assert app.view_state() == "getrennt"
    assert app.tiles["t"].value.cget("text") == "--"
    assert gui_env["transports"][0].closed or pump(lambda: gui_env["transports"][0].closed)
    gui_env["plugged"]["on"] = True
    assert pump(lambda: connected_with_values(app), timeout=10)
    assert len(gui_env["transports"]) == 2


def test_close_releases_port(gui_env):
    app, pump = gui_env["app"], gui_env["pump"]
    assert pump(lambda: app.connected)
    app.on_close()
    assert gui_env["transports"][-1].closed


def test_friendly_errors_use_the_one_table():
    from umwelt_ctl.gui import friendly_error
    from umwelt_ctl.protocol import ERROR_TEXTS_DE

    for code, text in ERROR_TEXTS_DE.items():
        assert friendly_error(DeviceError(code, "x")) == text
