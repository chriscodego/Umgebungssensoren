// history - RAM ring buffer of the last GRAPH_POINTS measurements per value for the
// on-device graph (PROJ-10). One point every GRAPH_STEP_S from the latest measurement;
// values in tenths (0.1 degC, 0.1 %rH, 0.1 hPa, 0.1 kOhm), invalid -> GRAPH_GAP.
// Never stored in EEPROM; lost on reset. Reads sensor_data(), never the bus.
#pragma once

#include "config.h"

const uint8_t HIST_VALUES = 4;  // 0 temperature, 1 humidity, 2 pressure, 3 gas (tile order)

void history_begin();                      // all points = gaps (setup() only)
void history_poll(uint32_t now);           // take a point when GRAPH_STEP_S has passed
int16_t history_get(uint8_t value, uint8_t i);  // i = 0 oldest .. GRAPH_POINTS-1 newest
uint8_t history_generation();              // incremented on every new point
