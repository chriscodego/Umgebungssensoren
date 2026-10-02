import re
import threading
import time

import pytest

from umwelt_ctl import device
from umwelt_ctl.device import (
    DeviceDisconnected,
    DeviceTimeout,
    FirmwareTooOld,
    PortBusy,
    UmweltDevice,
)
from umwelt_ctl.protocol import DeviceError, DeviceStatus, Event, Measurement, ProtocolError

from conftest import FakeTransport, FakeUmwelt


def collect_events(dev):
    events: list[Event] = []
    dev.subscribe(events.append)
    return events


def wait_for(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


# --------------------------------------------------------------------------- basic commands


def test_ping_status_read(make_device):
    dev, tr = make_device(FakeUmwelt())
    assert dev.ping() == "0.1.0"
    assert dev.status() == DeviceStatus("OK", 10, 100, 0, 0)
    assert dev.read() == Measurement(2134, 4512, 10132, 85000, 3)
    assert tr.written == ["PING", "STATUS", "READ"]


def test_wrong_product_is_rejected(make_device):
    dev, _ = make_device(lambda cmd: "OK PONG GloveboxControl 0.4.0")
    with pytest.raises(ProtocolError, match="falscher Port"):
        dev.ping()


def test_read_with_sensor_missing_raises_err5(make_device):
    model = FakeUmwelt()
    model.sensor = "MISSING"
    dev, _ = make_device(model)
    with pytest.raises(DeviceError) as ei:
        dev.read()
    assert ei.value.code == 5
    assert "Sensor nicht verfügbar" in str(ei.value)
    assert dev.status().sensor == "MISSING"


def test_config_list_with_evt_between_list_lines(make_device):
    model = FakeUmwelt()
    model.cfg_interleave = ["EVT DATA 2200 4000 10100 90000", "EVT ALARM 1 1",
                            "EVT DATA kaputt 1 2 3"]
    dev, _ = make_device(model)
    events = collect_events(dev)
    cfg = dev.get_config()
    assert cfg == {"INTERVAL": 10, "TEMP_OFFSET": 0, "T_HI": None, "T_LO": None,
                   "RH_HI": None, "RH_LO": None, "BUZZER": 0}
    assert wait_for(lambda: len(events) == 2)
    time.sleep(0.05)
    assert [e.kind for e in events] == ["DATA", "ALARM"]  # garbage DATA skipped
    assert events[0].measurement == Measurement(2200, 4000, 10100, 90000)


def test_config_set_and_reset(make_device):
    model = FakeUmwelt()
    dev, tr = make_device(model)
    dev.set_config("T_HI", "2850")
    dev.set_config("RH_LO", "OFF")
    assert model.cfg["T_HI"] == 2850
    dev.reset_config()
    assert model.cfg["T_HI"] is None
    assert tr.written == ["CFG T_HI 2850", "CFG RH_LO OFF", "CFG RESET"]


@pytest.mark.parametrize("handler_reply,code", [
    ("ERR 1 unknown", 1), ("ERR 2 args", 2), ("ERR 3 range", 3), ("ERR 5 sensor", 5),
    ("ERR 7 state", 7),
])
def test_err_codes_raise_device_error_with_german_text(make_device, handler_reply, code):
    from umwelt_ctl.protocol import ERROR_TEXTS_DE

    dev, tr = make_device(lambda cmd: handler_reply)
    with pytest.raises(DeviceError) as ei:
        dev.ack()
    assert ei.value.code == code
    assert ERROR_TEXTS_DE[code] in str(ei.value)
    tr.handler = FakeUmwelt()
    assert dev.ping() == "0.1.0"  # still usable afterwards


def test_ack_without_alarm_is_err7_and_with_alarm_ok(make_device):
    model = FakeUmwelt()
    dev, _ = make_device(model)
    with pytest.raises(DeviceError) as ei:
        dev.ack()
    assert ei.value.code == 7
    model.raise_alarm(1)
    dev.ack()
    assert model.unacked == 0


def test_err_inside_list(make_device):
    dev, _ = make_device(lambda cmd: ["OK", "C INTERVAL 10", "ERR 2 kaputt"])
    with pytest.raises(DeviceError) as ei:
        dev.get_config()
    assert ei.value.code == 2


def test_chunked_input_and_events_before_response(make_device):
    def handler(cmd):
        return ["EVT SENSOR OK", "OK OK 30 5 0 0"]

    dev, _ = make_device(handler, chunk_size=3)
    events = collect_events(dev)
    assert dev.status() == DeviceStatus("OK", 30, 5)
    assert wait_for(lambda: events and events[0] == Event("SENSOR", sensor="OK"))


def test_stream_and_data_events(make_device):
    model = FakeUmwelt()
    dev, tr = make_device(model)
    events = collect_events(dev)
    dev.set_stream(True)
    model.measure((-512, 9999, 9876, 120000))
    model.sensor = "MISSING"
    model.measure()
    assert wait_for(lambda: len(events) == 2)
    assert events[0].measurement == Measurement(-512, 9999, 9876, 120000)
    assert events[1].measurement == Measurement()  # all '-' -> invalid, not 0
    assert tr.written == ["STREAM 1"]


def test_invalid_event_data_is_skipped(make_device):
    dev, tr = make_device(FakeUmwelt())
    events = collect_events(dev)
    tr.send("EVT DATA 1 2 3", "EVT DATA a b c d", "EVT FUTURE 1", "EVT ALARM 99 1",
            "EVT DATA 2000 5000 10000 1000")
    assert wait_for(lambda: len(events) == 1)
    time.sleep(0.05)
    assert [e.kind for e in events] == ["DATA"]


def test_invalid_utf8_does_not_crash(make_device):
    holder = {}

    def handler(cmd):
        holder["tr"].inject_bytes(b"\xff\xfe\r\nOK PONG Umgebungssensoren 0.1.\xc3\r\n")

    dev, tr = make_device(handler)
    holder["tr"] = tr
    assert dev.ping().startswith("0.1.")


def test_time_get_set_and_sync(make_device):
    import datetime as dt

    model = FakeUmwelt()
    dev, tr = make_device(model)
    assert dev.get_time() is None
    dev._now = lambda: dt.datetime(2026, 10, 2, 14, 3, 12, 0)
    sent = dev.sync_time(sleep=lambda s: None)
    assert sent == dt.datetime(2026, 10, 2, 14, 3, 12)
    assert tr.written[-1] == "TIME 14:03:12"
    assert dev.get_time() == dt.time(14, 3, 12)


# --------------------------------------------------------------------------- timeouts & robustness


def test_timeout_no_answer(make_device):
    dev, _ = make_device(lambda cmd: None, timeout=0.2)
    t0 = time.monotonic()
    with pytest.raises(DeviceTimeout, match="antwortet nicht"):
        dev.ping()
    assert time.monotonic() - t0 < 1.0


def test_timeout_missing_end(make_device):
    dev, _ = make_device(lambda cmd: ["OK", "C INTERVAL 10"], timeout=0.2)
    with pytest.raises(DeviceTimeout):
        dev.get_config()


def test_late_answer_after_timeout_is_not_misattributed(make_device):
    holder = {}

    def handler(cmd):
        if cmd == "READ":
            threading.Timer(0.3, lambda: holder["tr"].send("OK 1 2 3000 4 5")).start()
            return None
        return "OK PONG Umgebungssensoren 0.1.0"

    dev, tr = make_device(handler, timeout=0.2)
    holder["tr"] = tr
    with pytest.raises(DeviceTimeout):
        dev.read()
    assert dev.ping() == "0.1.0"


def test_noise_before_response_is_skipped(make_device):
    dev, _ = make_device(lambda cmd: ["\x00garbage", "OK PONG Umgebungssensoren 0.1.0"])
    assert dev.ping() == "0.1.0"


def test_disconnect_fails_pending_request_and_notifies(make_device):
    dev, tr = make_device(lambda cmd: None, timeout=5.0)
    events = collect_events(dev)
    threading.Timer(0.1, tr.fail).start()
    with pytest.raises(DeviceDisconnected):
        dev.ping()
    assert wait_for(lambda: events and events[-1].kind == "DISCONNECTED")
    assert not dev.connected
    with pytest.raises(DeviceDisconnected):
        dev.ping()


def test_close_releases_port():
    tr = FakeTransport(FakeUmwelt())
    with UmweltDevice(tr, timeout=1.0) as dev:
        dev.start()
        assert dev.ping() == "0.1.0"
    assert tr.closed
    with pytest.raises(DeviceDisconnected):
        dev.ping()


def test_concurrent_requests_are_serialized(make_device):
    dev, _ = make_device(FakeUmwelt())
    errors, results = [], []

    def worker():
        try:
            for _ in range(15):
                results.append((dev.ping(), dev.status().interval, len(dev.get_config())))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert results == [("0.1.0", 10, 7)] * 60


# --------------------------------------------------------------------------- ready check


def test_ready_without_reset_blank_line_then_quick_ping(make_device):
    dev, tr = make_device(FakeUmwelt())
    t0 = time.monotonic()
    assert dev.wait_ready(boot_wait=3.0) == "0.1.0"
    assert time.monotonic() - t0 < 1.5  # did not wait for a boot
    assert tr.raw_written[0] == b"\n"   # blank line first
    assert tr.written == ["PING"]


def test_ready_when_board_announces_boot(make_device):
    dev, tr = make_device(FakeUmwelt())
    tr.send("EVT BOOT 0.1.0")
    t0 = time.monotonic()
    assert dev.wait_ready(boot_wait=3.0) == "0.1.0"
    assert time.monotonic() - t0 < 1.0
    assert tr.written == ["PING"]
    time.sleep(0.2)
    assert "STATUS" not in tr.written  # the BOOT of the ready check is not a restart


def test_ready_when_board_resets_anyway(make_device):
    model = FakeUmwelt()
    model.silent = True  # bootloader: no answer to the quick PING

    def boot():
        model.silent = False
        model.reboot()

    dev, tr = make_device(model)
    threading.Timer(1.0, boot).start()
    t0 = time.monotonic()
    assert dev.wait_ready(boot_wait=3.0) == "0.1.0"
    assert 0.9 < time.monotonic() - t0 < 2.5
    time.sleep(0.2)
    assert tr.written.count("PING") == 2
    assert "STATUS" not in tr.written


def test_ready_fails_cleanly_without_device(make_device):
    dev, _ = make_device(lambda cmd: None, timeout=0.2)
    with pytest.raises(DeviceTimeout):
        dev.wait_ready(boot_wait=0.3, ping_attempts=2)


def test_firmware_too_old(make_device):
    dev, _ = make_device(FakeUmwelt(fw="0.0.5"))
    with pytest.raises(FirmwareTooOld, match="zu alt"):
        dev.wait_ready(boot_wait=0.5)


def test_mid_session_boot_restores_status_time_and_stream(make_device):
    model = FakeUmwelt()
    dev, tr = make_device(model)
    dev.wait_ready(boot_wait=0.5)
    dev.set_stream(True)
    events = collect_events(dev)
    model.alarm = 16
    model.reboot()
    assert wait_for(lambda: events and events[0].kind == "BOOT")
    after = tr.written[tr.written.index("STREAM 1") + 1:]
    assert after[0] == "STATUS"
    assert re.fullmatch(r"TIME \d\d:\d\d:\d\d", after[1])
    assert after[2] == "STREAM 1"
    assert model.stream and model.clock is not None
    assert dev.last_status is not None and dev.last_status.alarm_flags == 16
    assert dev.boot_count == 1


# --------------------------------------------------------------------------- port handling


class _RecordingSerial:
    instances: list = []
    fail_with: Exception | None = None

    def __init__(self):
        self.log: list[tuple[str, object]] = []
        _RecordingSerial.instances.append(self)

    def __setattr__(self, name, value):
        if name != "log":
            self.log.append((name, value))
        object.__setattr__(self, name, value)

    def open(self):
        self.log.append(("open", None))
        if _RecordingSerial.fail_with is not None:
            raise _RecordingSerial.fail_with

    def close(self):
        self.log.append(("close", None))


def test_serial_transport_opens_without_reset(monkeypatch):
    import serial

    _RecordingSerial.instances, _RecordingSerial.fail_with = [], None
    monkeypatch.setattr(serial, "Serial", _RecordingSerial)
    tr = device.SerialTransport("COM42")
    ser = _RecordingSerial.instances[0]
    names = [n for n, _ in ser.log]
    assert ("dtr", False) in ser.log and ("rts", False) in ser.log
    assert names.index("dtr") < names.index("open") and names.index("rts") < names.index("open")
    assert ser.timeout and ser.timeout > 0  # always a read timeout
    assert ser.baudrate == 115200
    tr.close()
    assert ser.log[-1] == ("close", None)


def test_port_busy_gives_german_message(monkeypatch):
    import serial

    _RecordingSerial.instances = []
    _RecordingSerial.fail_with = serial.SerialException(
        "could not open port 'COM9': PermissionError(13, 'Zugriff verweigert', None, 5)")
    monkeypatch.setattr(serial, "Serial", _RecordingSerial)
    try:
        with pytest.raises(PortBusy, match="belegt"):
            UmweltDevice.open("COM9")
    finally:
        _RecordingSerial.fail_with = None


def test_missing_port_gives_german_message(monkeypatch):
    import serial

    _RecordingSerial.fail_with = serial.SerialException("could not open port 'COM77': "
                                                        "FileNotFoundError")
    monkeypatch.setattr(serial, "Serial", _RecordingSerial)
    try:
        with pytest.raises(DeviceDisconnected, match="kann nicht geöffnet werden"):
            UmweltDevice.open("COM77")
    finally:
        _RecordingSerial.fail_with = None


def test_detect_port_precedence(monkeypatch):
    monkeypatch.setattr(device, "find_ports", lambda vid=0x2341: [("COM5", "Arduino Uno")])
    monkeypatch.setenv("UMWELT_PORT", "COM9")
    assert device.detect_port("COM3") == "COM3"   # --port wins
    assert device.detect_port() == "COM9"         # then UMWELT_PORT
    monkeypatch.delenv("UMWELT_PORT")
    assert device.detect_port() == "COM5"         # then USB VID 0x2341
    monkeypatch.setattr(device, "find_ports", lambda vid=0x2341: [])
    with pytest.raises(DeviceDisconnected, match="Kein Arduino"):
        device.detect_port()


def test_find_ports_filters_vid(monkeypatch):
    from serial.tools import list_ports

    class Info:
        def __init__(self, dev, vid):
            self.device, self.vid, self.description = dev, vid, "x"

    monkeypatch.setattr(list_ports, "comports",
                        lambda: [Info("COM9", 0x2341), Info("COM1", None), Info("COM4", 0x1A86)])
    assert device.find_ports() == [("COM9", "x")]
    assert [x[2] for x in device.list_all_ports()] == [False, False, True]
