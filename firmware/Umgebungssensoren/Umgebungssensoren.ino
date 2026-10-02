// Umgebungssensoren - BME680 values (temperature, humidity, pressure, gas resistance) on a
// 160x128 touch display, threshold alarms, serial protocol for the optional PC tool.
// Contract: docs/SPEC.md. setup()/loop() only; logic lives in the modules.

#include "config.h"
#include "display.h"
#include "input.h"
#include "protocol.h"
#include "sensor.h"
#include "signal.h"
#include "storage.h"
#include "ui.h"

void setup() {
  protocol_begin();          // Serial first so nothing is lost
  input_begin();             // T_CS high before the display talks on the shared SPI bus
  signal_begin();
  storage_begin();           // EEPROM: validate, defaults if invalid (nothing written)
  display_begin();
  sensor_begin();            // I2C probe 0x76/0x77; missing sensor = state MISSING
  bool calibrate = input_pressedNow();  // touch held at power-up -> calibration
  ui_begin(calibrate);
  protocol_evtBoot();
  signal_evaluate(false);    // sensor missing at boot -> EVT ALARM 16 1 right away
}

void loop() {
  uint32_t now = millis();
  protocol_poll(now);        // serial commands (one line per pass)
  ui_update(now);            // touch -> pages; redraw what is dirty

  uint8_t ev = sensor_poll(now);  // BME680 state machine (trigger -> wait -> read)
  if (ev & SENSOR_EV_STATE) protocol_evtSensor(sensor_state());
  if (ev & SENSOR_EV_DATA) protocol_evtData();
  if (ev != 0) signal_evaluate((ev & SENSOR_EV_DATA) != 0);
  signal_update(now);        // buzzer pattern

  TouchDebug d;
  if (input_debugSample(d) && protocol_debugTouch()) {
    protocol_evtTouch(d.rawX, d.rawY, d.z, d.x, d.y);  // diagnostics, throttled
  }
}
