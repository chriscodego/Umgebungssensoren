#include "storage.h"

#include <avr/eeprom.h>

// avr-libc EEPROM functions instead of the EEPROM class: saves flash.
#define EE(a) ((uint8_t *)(uintptr_t)(a))

// EEPROM layout 1 (little-endian, docs/eeprom-layout-history.md), 29 B:
//   off 0   uint32  magic 0x554D5753 ("UMWS")
//   off 4   uint8   layout version (1)
//   off 5   Config  int16 interval, temp_offset, t_hi, t_lo, rh_hi, rh_lo; uint8 buzzer
//   off 18  uint8   CRC-8 over the Config bytes
//   off 19  TouchCal (9 B)
//   off 28  uint8   CRC-8 over TouchCal
const uint16_t ADDR_MAGIC   = EEPROM_BASE;
const uint16_t ADDR_LAYOUT  = ADDR_MAGIC + 4;
const uint16_t ADDR_CFG     = ADDR_LAYOUT + 1;
const uint16_t ADDR_CFG_CRC = ADDR_CFG + sizeof(Config);
const uint16_t ADDR_CAL     = ADDR_CFG_CRC + 1;
const uint16_t ADDR_CAL_CRC = ADDR_CAL + sizeof(TouchCal);

static_assert(sizeof(Config) == 13 && sizeof(TouchCal) == 9, "EEPROM layout 1 changed");
static_assert(ADDR_CAL_CRC == 28, "EEPROM layout 1 changed");

Config g_cfg;
TouchCal g_cal;

static uint8_t s_generation = 0;

// Allowed range per int16 key (THR_OFF additionally for thresholds).
static const int16_t RANGE[CFG_WORDS][2] PROGMEM = {
    {INTERVAL_MIN, INTERVAL_MAX},       {TEMP_OFFSET_MIN, TEMP_OFFSET_MAX},
    {T_MIN, T_MAX},                     {T_MIN, T_MAX},
    {RH_MIN, RH_MAX},                   {RH_MIN, RH_MAX},
};

static uint8_t crc8(const uint8_t *p, uint8_t n) {
  uint8_t crc = 0;
  while (n--) {
    crc ^= *p++;
    for (uint8_t i = 0; i < 8; i++) crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
  }
  return crc;
}

bool storage_allowsOff(uint8_t key) { return key >= CFG_T_HI && key <= CFG_RH_LO; }

// Single value check (range or OFF).
static bool valueOk(uint8_t key, int16_t v) {
  if (key == CFG_BUZZER) return v == 0 || v == 1;
  if (key >= CFG_WORDS) return false;
  if (v == THR_OFF) return storage_allowsOff(key);
  return v >= (int16_t)pgm_read_word(&RANGE[key][0]) && v <= (int16_t)pgm_read_word(&RANGE[key][1]);
}

// Low threshold must stay below the high one (both set).
static bool pairOk(const Config &c, uint8_t hi) {
  int16_t h = c.val[hi], l = c.val[hi + 1];
  return h == THR_OFF || l == THR_OFF || l < h;
}

static bool configOk(const Config &c) {
  for (uint8_t k = 0; k < CFG_WORDS; k++) {
    if (!valueOk(k, c.val[k])) return false;
  }
  return valueOk(CFG_BUZZER, c.buzzer) && pairOk(c, CFG_T_HI) && pairOk(c, CFG_RH_HI);
}

static void defaultConfig() {
  g_cfg.val[CFG_INTERVAL] = INTERVAL_DEFAULT;
  g_cfg.val[CFG_TEMP_OFFSET] = 0;
  for (uint8_t k = CFG_T_HI; k <= CFG_RH_LO; k++) g_cfg.val[k] = THR_OFF;
  g_cfg.buzzer = BUZZER_DEFAULT;
}

void storage_defaultCal(TouchCal &c) {
  c.left = CAL_DEFAULT_LEFT;
  c.right = CAL_DEFAULT_RIGHT;
  c.top = CAL_DEFAULT_TOP;
  c.bottom = CAL_DEFAULT_BOTTOM;
  c.flags = CAL_DEFAULT_SWAP ? CAL_FLAG_SWAP : 0;
}

static bool calInRange(int16_t v) { return v >= CAL_RAW_LIMIT_LO && v <= CAL_RAW_LIMIT_HI; }

bool storage_calValid(const TouchCal &c) {
  if (c.flags & (uint8_t)~(CAL_FLAG_SWAP | CAL_FLAG_USER)) return false;
  if (!calInRange(c.left) || !calInRange(c.right) || !calInRange(c.top) || !calInRange(c.bottom)) {
    return false;
  }
  return abs(c.right - c.left) >= CAL_MIN_SPAN && abs(c.bottom - c.top) >= CAL_MIN_SPAN;
}

// Header + config + CRC (update semantics: only changed bytes are written).
static void saveConfig() {
  eeprom_update_block(&EEPROM_MAGIC, EE(ADDR_MAGIC), sizeof(EEPROM_MAGIC));
  eeprom_update_byte(EE(ADDR_LAYOUT), EEPROM_LAYOUT);
  eeprom_update_block(&g_cfg, EE(ADDR_CFG), sizeof(g_cfg));
  eeprom_update_byte(EE(ADDR_CFG_CRC), crc8((const uint8_t *)&g_cfg, sizeof(g_cfg)));
  s_generation++;
}

void storage_saveCal() {
  // The calibration block is only meaningful under a valid header: write it too.
  eeprom_update_block(&EEPROM_MAGIC, EE(ADDR_MAGIC), sizeof(EEPROM_MAGIC));
  eeprom_update_byte(EE(ADDR_LAYOUT), EEPROM_LAYOUT);
  eeprom_update_block(&g_cal, EE(ADDR_CAL), sizeof(g_cal));
  eeprom_update_byte(EE(ADDR_CAL_CRC), crc8((const uint8_t *)&g_cal, sizeof(g_cal)));
}

void storage_begin() {
  uint32_t magic = 0;
  eeprom_read_block(&magic, EE(ADDR_MAGIC), sizeof(magic));
  bool header = magic == EEPROM_MAGIC && eeprom_read_byte(EE(ADDR_LAYOUT)) == EEPROM_LAYOUT;
  bool cfgOk = false, calOk = false;
  if (header) {
    eeprom_read_block(&g_cfg, EE(ADDR_CFG), sizeof(g_cfg));
    cfgOk = eeprom_read_byte(EE(ADDR_CFG_CRC)) == crc8((const uint8_t *)&g_cfg, sizeof(g_cfg)) &&
            configOk(g_cfg);
    eeprom_read_block(&g_cal, EE(ADDR_CAL), sizeof(g_cal));
    calOk = eeprom_read_byte(EE(ADDR_CAL_CRC)) == crc8((const uint8_t *)&g_cal, sizeof(g_cal)) &&
            storage_calValid(g_cal) && (g_cal.flags & CAL_FLAG_USER);
  }
  if (!cfgOk) defaultConfig();
  if (!calOk) storage_defaultCal(g_cal);
  s_generation++;
}

int16_t storage_get(uint8_t key) {
  if (key == CFG_BUZZER) return g_cfg.buzzer;
  return key < CFG_WORDS ? g_cfg.val[key] : 0;
}

bool storage_set(uint8_t key, int16_t v) {
  if (!valueOk(key, v)) return false;
  Config c = g_cfg;
  if (key == CFG_BUZZER) {
    c.buzzer = (uint8_t)v;
  } else {
    c.val[key] = v;
  }
  if (!pairOk(c, CFG_T_HI) || !pairOk(c, CFG_RH_HI)) return false;
  if (memcmp(&c, &g_cfg, sizeof(c)) != 0) {
    g_cfg = c;
    saveConfig();
  }
  return true;
}

void storage_resetConfig() {
  defaultConfig();
  saveConfig();
}

uint8_t storage_generation() { return s_generation; }
