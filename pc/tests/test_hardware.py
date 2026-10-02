"""Hardware-in-the-loop tests. Only with ``python -m pytest pc/tests -m hardware``.

Port: env var ``UMWELT_PORT`` (default COM9). Only one program may hold the port — close
GUI/monitor/Arduino IDE first. Values are checked against plausibility ranges, never exact
numbers. The configuration is read first and restored afterwards; the alarm thresholds are
not changed.
"""

import os
import queue
import time

import pytest

from umwelt_ctl import protocol as p
from umwelt_ctl.device import UmweltDevice

pytestmark = pytest.mark.hardware

PORT = os.environ.get("UMWELT_PORT", "COM9")


def test_open_does_not_reset_the_board():
    """Runs first, before the module fixture holds the port."""
    with UmweltDevice.open(PORT) as d1:
        before = d1.status().uptime_sec
    time.sleep(1.5)
    with UmweltDevice.open(PORT) as d2:
        after = d2.status().uptime_sec
        assert d2.boot_count == 0
    assert after >= before + 1  # uptime continued -> opening did not reset the Uno


@pytest.fixture(scope="module")
def dev():
    d = UmweltDevice.open(PORT)
    saved = d.get_config()
    try:
        yield d
    finally:
        try:
            d.set_stream(False)
            current = d.get_config()
            for key, value in saved.items():
                if current.get(key) != value:
                    d.set_config(key, p.CFG_OFF if value is None else str(value))
        finally:
            d.close()


def test_ping(dev):
    assert dev.ping()


def test_status_and_read_plausible(dev):
    st = dev.status()
    assert st.sensor in p.SENSOR_STATES
    assert 1 <= st.interval <= 3600
    if st.sensor == p.SENSOR_MISSING:
        pytest.skip("Sensor fehlt – Messwert-Plausibilität nicht prüfbar")
    m = dev.read()
    if m.temperature_c is not None:
        assert -20 <= m.temperature_c <= 60
    if m.humidity_pct is not None:
        assert 0 <= m.humidity_pct <= 100
    if m.pressure_hpa is not None:
        assert 800 <= m.pressure_hpa <= 1100
    if m.gas is not None:
        assert m.gas > 0


def test_config_round_trip(dev):
    cfg = dev.get_config()
    assert set(cfg) == set(p.CONFIG_KEYS)
    old = cfg["INTERVAL"]
    new = 7 if old != 7 else 8
    dev.set_config("INTERVAL", str(new))
    assert dev.get_config()["INTERVAL"] == new
    dev.set_config("INTERVAL", str(old))


def test_error_codes(dev):
    from umwelt_ctl.protocol import DeviceError

    for cmd, code in (("FOO", 1), ("CFG INTERVAL abc", 2), ("CFG INTERVAL 0", 3),
                      ("STREAM 2", 2), ("TIME 25:00:00", 2)):
        with pytest.raises(DeviceError) as ei:
            dev.request(cmd)
        assert ei.value.code == code, cmd


def test_time_sync(dev):
    sent = dev.sync_time()
    got = dev.get_time()
    assert got is not None
    assert abs(p.clock_difference_sec(got, sent.time())) <= 2


def test_stream_delivers_data(dev):
    st = dev.status()
    if st.sensor == p.SENSOR_MISSING:
        pytest.skip("Sensor fehlt")
    events: queue.Queue = queue.Queue()
    unsubscribe = dev.subscribe(events.put)
    try:
        dev.set_stream(True)
        end = time.monotonic() + st.interval + 5
        while True:
            ev = events.get(timeout=max(0.1, end - time.monotonic()))
            if ev.kind == p.EVT_DATA:
                assert ev.measurement is not None
                break
    finally:
        dev.set_stream(False)
        unsubscribe()
