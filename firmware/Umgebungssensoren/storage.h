// storage - persistent configuration and touch calibration in EEPROM (layout 1, see
// docs/SPEC.md "EEPROM" and docs/eeprom-layout-history.md). Mirrored in RAM.
// Measurements are never written to the EEPROM.
#pragma once

#include "config.h"

// Configuration keys; the index is also the order in the EEPROM and in "CFG" output.
enum CfgKey : uint8_t {
  CFG_INTERVAL = 0,   // s, 1..3600
  CFG_TEMP_OFFSET,    // 0.01 degC, -5000..5000
  CFG_T_HI,           // 0.01 degC or THR_OFF
  CFG_T_LO,
  CFG_RH_HI,          // 0.01 %rH or THR_OFF
  CFG_RH_LO,
  CFG_BUZZER,         // 0/1
  CFG_KEYS
};

const uint8_t CFG_WORDS = CFG_BUZZER;  // number of int16 fields before the buzzer byte

struct Config {          // 13 bytes, little-endian, no padding on AVR
  int16_t val[CFG_WORDS];
  uint8_t buzzer;
};

// Raw touch value at the screen edges (x = 0 / SCREEN_W-1, y = 0 / SCREEN_H-1).
struct TouchCal {
  int16_t left, right, top, bottom;
  uint8_t flags;  // CAL_FLAG_*
};

const uint8_t CAL_FLAG_SWAP = 0x01;  // raw Y axis drives screen X
const uint8_t CAL_FLAG_USER = 0x80;  // set by an on-device calibration

extern Config g_cfg;
extern TouchCal g_cal;

// Load + validate (magic, layout, CRC, every range). Invalid -> defaults in RAM only;
// nothing is written at boot (the EEPROM is only written when a setting changes).
void storage_begin();

int16_t storage_get(uint8_t key);
// Range check (incl. low < high for threshold pairs) and save if changed.
// Returns false if the value is not allowed for this key (-> ERR 3).
bool storage_set(uint8_t key, int16_t v);
bool storage_allowsOff(uint8_t key);
void storage_resetConfig();          // defaults + save (touch calibration is kept)

void storage_saveCal();
void storage_defaultCal(TouchCal &c);
bool storage_calValid(const TouchCal &c);

// Incremented on every config change (display invalidation).
uint8_t storage_generation();
