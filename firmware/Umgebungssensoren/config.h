// Umgebungssensoren - central configuration.
// Every pin, I2C address, limit, timing and FW_VERSION lives here (contract: docs/SPEC.md).
#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------- version
#define FW_VERSION "0.1.0"
#define FW_NAME    "Umgebungssensoren"

// ---------------------------------------------------------------- pins (SPEC.md "Hardware")
// Shared hardware SPI bus: MOSI D11, MISO D12, SCK D13. I2C: SDA A4, SCL A5 (own TWI master).
const uint8_t PIN_TFT_CS    = 10;  // display chip select (via level shifter)
const uint8_t PIN_TFT_DC    = 9;   // display A0 / DC
const uint8_t PIN_TFT_RST   = 8;   // display RESET
const uint8_t PIN_TOUCH_CS  = 4;   // XPT2046 T_CS
const uint8_t PIN_TOUCH_IRQ = 2;   // XPT2046 T_IRQ, active LOW
const uint8_t PIN_BUZZER    = 5;   // passive piezo (Timer2 square wave, see signal.cpp)

// ---------------------------------------------------------------- display
// ST7735R tab variant of the Joy-IT RB-TFT1.8-T (as confirmed on GloveboxControl hardware).
#define TFT_INIT_VARIANT INITR_BLACKTAB
const uint8_t  TFT_ROTATION = 1;          // landscape: 160 wide x 128 high
const uint32_t TFT_SPI_HZ   = 8000000UL;  // Uno max (F_CPU/2)
const int16_t  SCREEN_W     = 160;
const int16_t  SCREEN_H     = 128;

// Display texts use the GFX classic font in CP437 mode (tft.cp437(true)). End the literal
// after a hex escape ("Zur" UE_ "ck") so it cannot swallow following hex digits.
#define AE_ "\x84"
#define OE_ "\x94"
#define UE_ "\x81"
#define UE_UC "\x9A"
#define DEG_ "\xF8"    // degree sign
#define OHM_ "\xEA"    // capital omega
const char GLYPH_UP    = 0x18;  // CP437 arrows (gas trend)
const char GLYPH_DOWN  = 0x19;
const char GLYPH_RIGHT = 0x1A;

// ---------------------------------------------------------------- BME680 (sensor.cpp)
const uint8_t  BME_ADDR_PRIMARY   = 0x76;     // probed first (SDO low)
const uint8_t  BME_ADDR_SECONDARY = 0x77;     // SDO high
const uint32_t I2C_CLOCK_HZ       = 100000UL;
const uint16_t I2C_SPIN_MAX       = 4000;     // TWI busy-wait bound (~1 ms): stuck bus -> error
const uint16_t SENSOR_RETRY_MS    = 5000;     // MISSING: probe again this often (SPEC)
const uint16_t SENSOR_RESET_MS    = 10;       // after soft reset (datasheet: 2 ms)
const uint16_t SENSOR_MEAS_WAIT_MS = 180;     // TPH (~21 ms) + gas heater (148 ms)
const uint16_t SENSOR_POLL_MS     = 10;       // then poll "new data" this often
const uint16_t SENSOR_MEAS_TIMEOUT_MS = 1000; // no new data by then -> ERROR
// Oversampling (register encodings): T x2, P x4, H x2; IIR filter off.
const uint8_t  BME_OSRS_T = 2;   // x2
const uint8_t  BME_OSRS_P = 3;   // x4
const uint8_t  BME_OSRS_H = 2;   // x2
// Gas heater profile (SPEC: 320 degC / 150 ms; register step gives 148 ms).
const uint16_t GAS_HEATER_TEMP_C  = 320;
const uint8_t  GAS_HEATER_MS      = 150;
const int8_t   GAS_AMBIENT_DEFAULT_C = 25;    // heater calculation until a valid reading
// Gas trend: exponential mean with weight 1/2^GAS_TREND_SHIFT; arrow when the new value
// deviates by more than 1/GAS_TREND_DIV of that mean.
const uint8_t  GAS_TREND_SHIFT    = 3;
const uint8_t  GAS_TREND_DIV      = 20;       // 5 %

// Plausibility (SPEC "Messwerte"): outside -> value invalid ("-").
const int16_t  T_MIN   = -4000;   // 0.01 degC
const int16_t  T_MAX   = 8500;
const int16_t  RH_MIN  = 0;       // 0.01 %rH
const int16_t  RH_MAX  = 10000;
const uint16_t P_MIN   = 3000;    // 0.1 hPa
const uint16_t P_MAX   = 11000;

// ---------------------------------------------------------------- configuration (EEPROM)
const int16_t  INTERVAL_MIN      = 1;      // s
const int16_t  INTERVAL_MAX      = 3600;
const int16_t  INTERVAL_DEFAULT  = 10;
const int16_t  TEMP_OFFSET_MIN   = -5000;  // 0.01 degC
const int16_t  TEMP_OFFSET_MAX   = 5000;
const int16_t  THR_OFF           = -32768; // threshold switched off ("OFF")
const uint8_t  BUZZER_DEFAULT    = 0;
// Interval steps of the +/- buttons on the settings page (SPEC "Anzeige").
const uint16_t INTERVAL_STEPS[] PROGMEM = {1, 2, 5, 10, 30, 60};
const uint8_t  INTERVAL_STEP_COUNT = 6;

const uint32_t EEPROM_MAGIC  = 0x554D5753UL;  // "UMWS"
const uint8_t  EEPROM_LAYOUT = 1;             // bump on every struct change (user approval!)
const uint16_t EEPROM_BASE   = 0;

// ---------------------------------------------------------------- alarm (signal.cpp)
const uint8_t  ALARM_T_HI   = 1;    // flag values = SPEC bit mask
const uint8_t  ALARM_T_LO   = 2;
const uint8_t  ALARM_RH_HI  = 4;
const uint8_t  ALARM_RH_LO  = 8;
const uint8_t  ALARM_SENSOR = 16;
const uint8_t  ALARM_SET_COUNT = 2;     // consecutive violating measurements to set
const int16_t  ALARM_T_HYST   = 50;     // 0.5 degC back inside to clear
const int16_t  ALARM_RH_HYST  = 200;    // 2 %rH back inside to clear

// ---------------------------------------------------------------- buzzer
const uint16_t BUZZER_FREQ_HZ  = 2700;
const uint16_t BUZZER_BEEP_MS  = 150;
const uint16_t BUZZER_GAP_MS   = 150;
const uint8_t  BUZZER_BEEPS    = 3;       // per burst
const uint16_t BUZZER_REPEAT_MS = 10000;  // burst repeated while an alarm is unacknowledged

// ---------------------------------------------------------------- serial protocol
const uint32_t SERIAL_BAUD     = 115200;
const uint8_t  LINE_MAX        = 80;     // max command line length (BYTES, without \n)
const uint8_t  MAX_TOKENS      = 3;      // more tokens than this -> ERR 2
const uint16_t DEBUG_TOUCH_MS  = 100;    // DEBUG TOUCH: at most one EVT TOUCH per interval
const int16_t  TEST_INSET      = 10;     // TESTPATTERN: corner crosses inset from the edges
const uint32_t PC_INDICATOR_MS = 5000;   // "PC" mark shown this long after the last command

// ---------------------------------------------------------------- touch (XPT2046)
const uint16_t TOUCH_POLL_MS       = 10;    // sampling interval
const uint16_t TOUCH_DEBOUNCE_MS   = 30;    // press must be stable this long
const uint16_t TOUCH_RELEASE_MS    = 60;    // release must be stable this long
const uint16_t TOUCH_LOCKOUT_MS    = 150;   // ignore input after a screen change
const int16_t  TOUCH_Z_MIN         = 400;   // pressure threshold
const uint32_t TOUCH_SPI_HZ        = 2000000UL;  // XPT2046 max ~2.5 MHz
const int16_t  TOUCH_Z_PEAK_DIV    = 2;     // within a press: z < peak/2 counts as lifted
const int16_t  TOUCH_RAW_MIN       = 50;    // plausible raw 12-bit window; outside = ghost
const int16_t  TOUCH_RAW_MAX       = 4050;
const int16_t  TOUCH_HIT_PAD       = 2;     // hit boxes grow by this on every side
const int16_t  TOUCH_EDGE_SNAP     = 4;     // rect this close to the glass edge: hit box
                                            // extends to the edge (clamped coordinates)
const uint16_t TOUCH_REARM_MS      = 250;   // idle: re-arm XPT2046 PENIRQ this often
// 0: the XPT2046 has its own pull-up to 3.3 V; the AVR pull-up would pull PENIRQ to 5 V.
#define TOUCH_IRQ_PULLUP 0

// Touch calibration defaults (raw value at screen edge x=0 / x=159 / y=0 / y=127),
// measured on the Joy-IT RB-TFT1.8-T (GloveboxControl, 2026-09-30): raw X grows
// left->right, raw Y is INVERTED, no axis swap. Used until calibrated on the device.
const int16_t CAL_DEFAULT_LEFT   = 245;
const int16_t CAL_DEFAULT_RIGHT  = 3820;
const int16_t CAL_DEFAULT_TOP    = 3900;
const int16_t CAL_DEFAULT_BOTTOM = 230;
const uint8_t CAL_DEFAULT_SWAP   = 0;       // 1 = raw Y drives screen X
const int16_t CAL_MARGIN         = 15;      // crosshair distance from the screen edge
const int16_t CAL_MIN_SPAN       = 1000;    // min raw span across the screen per axis
const int16_t CAL_RAW_LIMIT_LO   = -2000;   // plausible extrapolated edge values
const int16_t CAL_RAW_LIMIT_HI   = 6000;

// ---------------------------------------------------------------- UI
const int16_t  STATUS_H          = 11;      // status line (clock, sensor state, PC)
const int16_t  TILE_Y            = 12;      // 2 x 2 value tiles below the status line
const int16_t  TILE_W            = 80;
const int16_t  TILE_H            = 45;
const int16_t  TAB_Y             = 104;     // page bar at the bottom (targets 24 px high)
const int16_t  TAB_H             = 24;
const uint16_t BLINK_MS          = 500;     // unacknowledged alarm blink half-period
const uint16_t REDRAW_MS         = 250;     // overview refresh check
const uint16_t CONFIRM_MS        = 3000;    // "Standard" needs a 2nd tap within this time
const uint32_t UI_IDLE_TIMEOUT_MS = 60000;  // settings without touch -> back to overview
const uint32_t CAL_IDLE_TIMEOUT_MS = 30000; // calibration without touch -> abort
