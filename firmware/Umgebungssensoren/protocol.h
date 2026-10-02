// protocol - line-based serial protocol (docs/SPEC.md "Serielles Protokoll", version 1).
// Owns all Serial output: responses and EVT lines. Never draws on the display.
// Also keeps the RAM-only wall clock (TIME) and the uptime counter.
#pragma once

#include "config.h"

// Error codes (SPEC "Fehlercodes"); 4 and 6 are reserved/unused.
enum ErrCode : uint8_t { E_OK = 0, E_UNKNOWN = 1, E_ARGS = 2, E_RANGE = 3, E_SENSOR = 5, E_STATE = 7 };

void protocol_begin();
// Non-blocking: reads available bytes; executes at most one complete line per call.
void protocol_poll(uint32_t now);
// Move received bytes into the line buffer without executing anything (long drawing).
void protocol_pump();
// True while a command arrived within the last PC_INDICATOR_MS.
bool protocol_pcActive(uint32_t now);

// Events
void protocol_evtBoot();
void protocol_evtSensor(uint8_t state);         // EVT SENSOR <OK|MISSING|ERROR>
void protocol_evtData();                        // EVT DATA ... (only with STREAM 1)
void protocol_evtAlarm(uint8_t flag, bool on);  // EVT ALARM <flag> <0|1>

// Diagnostics (SPEC "Diagnose", not part of the stable contract)
bool protocol_debugTouch();
void protocol_evtTouch(int16_t rawX, int16_t rawY, int16_t z, int16_t x, int16_t y);  // throttled

// Clock (RAM only, set by TIME) and uptime
bool clock_valid();
uint32_t clock_secOfDay();
uint32_t uptime_sec();
