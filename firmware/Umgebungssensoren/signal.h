// signal - alarm state (thresholds with hysteresis, sensor alarm, acknowledgement) and the
// piezo (own Timer2 driver). Emits EVT ALARM via protocol on every flag change.
#pragma once

#include "config.h"

void signal_begin();
// Re-evaluate the alarm flags. newData: a measurement completed (threshold counters
// advance only then); otherwise only sensor state and switched-off thresholds count.
void signal_evaluate(bool newData);
void signal_update(uint32_t now);  // buzzer pattern (non-blocking)
uint8_t signal_flags();            // active ALARM_* bits
uint8_t signal_unacked();          // active and not yet acknowledged
bool signal_ack();                 // false if there was nothing to acknowledge
