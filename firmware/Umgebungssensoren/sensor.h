// sensor - the ONLY module that knows the BME680 and the I2C bus (own TWI
// master on A4/A5, no Wire library).
// Own minimal driver with Bosch integer compensation (no library, no float).
// Non-blocking state machine: probe -> soft reset -> calibration/config -> idle ->
// trigger forced mode -> wait -> read -> compensate. A missing sensor is a normal state
// (MISSING, retried every SENSOR_RETRY_MS).
#pragma once

#include "config.h"

enum SensorState : uint8_t { SENSOR_OK = 0, SENSOR_MISSING = 1, SENSOR_ERROR = 2 };

// Validity bits of a measurement (an invalid value is shown/sent as "-", never 0).
const uint8_t VALID_T   = 0x01;
const uint8_t VALID_RH  = 0x02;
const uint8_t VALID_P   = 0x04;
const uint8_t VALID_GAS = 0x08;

struct Measurement {
  int16_t t;     // 0.01 degC (TEMP_OFFSET applied)
  uint16_t rh;   // 0.01 %rH
  uint16_t p;    // 0.1 hPa
  uint32_t gas;  // Ohm
  uint8_t valid; // VALID_* bits
};

// sensor_poll() result bits
const uint8_t SENSOR_EV_STATE = 0x01;  // sensor_state() changed
const uint8_t SENSOR_EV_DATA  = 0x02;  // a measurement completed (values may be invalid)

void sensor_begin();                 // I2C setup + first probe (setup() only)
uint8_t sensor_poll(uint32_t now);   // run the state machine; SENSOR_EV_* bits
uint8_t sensor_state();
uint8_t sensor_address();            // I2C address in use, 0 = none found
const Measurement &sensor_data();
bool sensor_hasData();               // a measurement completed since the sensor was found
uint32_t sensor_ageSec(uint32_t now);
int8_t sensor_gasTrend();            // +1 rising, -1 falling, 0 steady/unknown
uint8_t sensor_generation();         // incremented on every completed measurement / state change
