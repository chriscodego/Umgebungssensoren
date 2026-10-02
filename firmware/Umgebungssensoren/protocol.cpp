#include "protocol.h"

#include "sensor.h"
#include "signal.h"
#include "storage.h"
#include "ui.h"

// ------------------------------------------------------------------ line buffer
static char s_line[LINE_MAX + 1];
static uint8_t s_len = 0;
static bool s_overflow = false;
static bool s_ready = false;    // a complete line waits in s_line
static bool s_inCmd = false;    // s_line is being executed: pump must not touch it
static uint32_t s_lastCmdMs = 0;
static bool s_hadCmd = false;
static bool s_stream = false;   // STREAM 1: EVT DATA after every measurement
static bool s_debugTouch = false;
static uint32_t s_lastTouchEvt = 0;

// ------------------------------------------------------------------ clock / uptime
static bool s_clockValid = false;
static uint32_t s_clockSec = 0;   // second of the day
static uint32_t s_clockTick = 0;  // millis() of the last clock second
static uint32_t s_upSec = 0;
static uint32_t s_upTick = 0;

static void clockUpdate(uint32_t now) {
  // Counting whole seconds keeps both counters correct across the millis() wrap.
  while ((uint32_t)(now - s_upTick) >= 1000UL) {
    s_upTick += 1000UL;
    s_upSec++;
  }
  while ((uint32_t)(now - s_clockTick) >= 1000UL) {
    s_clockTick += 1000UL;
    if (++s_clockSec >= 86400UL) s_clockSec = 0;
  }
}

bool clock_valid() { return s_clockValid; }
uint32_t clock_secOfDay() { return s_clockSec; }
uint32_t uptime_sec() { return s_upSec; }

// ------------------------------------------------------------------ keywords + texts
static const char K_PING[] PROGMEM = "PING";
static const char K_STATUS[] PROGMEM = "STATUS";
static const char K_READ[] PROGMEM = "READ";
static const char K_CFG[] PROGMEM = "CFG";
static const char K_RESET[] PROGMEM = "RESET";
static const char K_OFF[] PROGMEM = "OFF";
static const char K_STREAM[] PROGMEM = "STREAM";
static const char K_ACK[] PROGMEM = "ACK";
static const char K_TIME[] PROGMEM = "TIME";
static const char K_DEBUG[] PROGMEM = "DEBUG";
static const char K_TOUCH[] PROGMEM = "TOUCH";
static const char K_TESTPATTERN[] PROGMEM = "TESTPATTERN";
static const char K_CAL[] PROGMEM = "CAL";
static const char K_SHOW[] PROGMEM = "SHOW";

// Config keys, index = CfgKey.
static const char C0[] PROGMEM = "INTERVAL";
static const char C1[] PROGMEM = "TEMP_OFFSET";
static const char C2[] PROGMEM = "T_HI";
static const char C3[] PROGMEM = "T_LO";
static const char C4[] PROGMEM = "RH_HI";
static const char C5[] PROGMEM = "RH_LO";
static const char C6[] PROGMEM = "BUZZER";
static const char *const CFG_NAME[CFG_KEYS] PROGMEM = {C0, C1, C2, C3, C4, C5, C6};

// Sensor states, index = SensorState.
static const char S0[] PROGMEM = "OK";
static const char S1[] PROGMEM = "MISSING";
static const char S2[] PROGMEM = "ERROR";
static const char *const STATE_NAME[] PROGMEM = {S0, S1, S2};

// Error texts, index = code - 1 (informative only; 4 and 6 unused).
static const char E1[] PROGMEM = "command";
static const char E2[] PROGMEM = "args";
static const char E3[] PROGMEM = "range";
static const char E5[] PROGMEM = "sensor";
static const char E7[] PROGMEM = "state";
static const char *const ERR_TEXT[] PROGMEM = {E1, E2, E3, E1, E5, E1, E7};

static const __FlashStringHelper *flashStr(const char *const *table, uint8_t i) {
  return (const __FlashStringHelper *)pgm_read_ptr(&table[i]);
}

// ------------------------------------------------------------------ output helpers
static void sendErr(uint8_t code) {
  if (code < E_UNKNOWN || code > E_STATE) code = E_UNKNOWN;
  Serial.print(F("ERR "));
  Serial.print(code);
  Serial.print(' ');
  Serial.println(flashStr(ERR_TEXT, (uint8_t)(code - 1)));
}

static void sendOk() { Serial.println(F("OK")); }

// " <v>" or " -"
static void printVal(bool valid, int32_t v) {
  Serial.print(' ');
  if (valid) {
    Serial.print(v);
  } else {
    Serial.print('-');
  }
}

static void printValues() {
  const Measurement &m = sensor_data();
  printVal(m.valid & VALID_T, m.t);
  printVal(m.valid & VALID_RH, m.rh);
  printVal(m.valid & VALID_P, m.p);
  Serial.print(' ');
  if (m.valid & VALID_GAS) {
    Serial.print(m.gas);  // uint32: printed unsigned
  } else {
    Serial.print('-');
  }
}

// ------------------------------------------------------------------ events
void protocol_evtBoot() { Serial.println(F("EVT BOOT " FW_VERSION)); }

void protocol_evtSensor(uint8_t state) {
  Serial.print(F("EVT SENSOR "));
  Serial.println(flashStr(STATE_NAME, state));
}

void protocol_evtData() {
  if (!s_stream) return;
  Serial.print(F("EVT DATA"));
  printValues();
  Serial.println();
}

void protocol_evtAlarm(uint8_t flag, bool on) {
  Serial.print(F("EVT ALARM "));
  Serial.print(flag);
  Serial.println(on ? F(" 1") : F(" 0"));
}

bool protocol_debugTouch() { return s_debugTouch; }

void protocol_evtTouch(int16_t rawX, int16_t rawY, int16_t z, int16_t x, int16_t y) {
  uint32_t now = millis();
  if ((uint32_t)(now - s_lastTouchEvt) < DEBUG_TOUCH_MS) return;
  s_lastTouchEvt = now;
  Serial.print(F("EVT TOUCH"));
  printVal(true, rawX);
  printVal(true, rawY);
  printVal(true, z);
  printVal(true, x);
  printVal(true, y);
  Serial.println();
}

// ------------------------------------------------------------------ argument parsing
static bool is(const char *tok, const char *kw_P) { return strcasecmp_P(tok, kw_P) == 0; }

// Optional '-', then 1..6 decimal digits.
static bool parseInt(const char *s, int32_t &out) {
  bool neg = *s == '-';
  if (neg) s++;
  if (*s == '\0') return false;
  int32_t v = 0;
  for (uint8_t n = 0; s[n] != '\0'; n++) {
    if (s[n] < '0' || s[n] > '9' || n >= 6) return false;
    v = v * 10 + (s[n] - '0');
  }
  out = neg ? -v : v;
  return true;
}

// Flag argument 0|1 as the only argument after the command word(s).
static bool parseFlag(char **t, uint8_t n, uint8_t idx, bool &out) {
  int32_t v;
  if (n != idx + 1 || !parseInt(t[idx], v) || v < 0 || v > 1 || t[idx][0] == '-') return false;
  out = v != 0;
  return true;
}

// ------------------------------------------------------------------ command handlers
// Each handler returns an error code; E_OK means it already sent its response.

static uint8_t cmdStatus(uint8_t n) {
  if (n != 1) return E_ARGS;
  Serial.print(F("OK "));
  Serial.print(flashStr(STATE_NAME, sensor_state()));
  printVal(true, g_cfg.val[CFG_INTERVAL]);
  printVal(true, (int32_t)uptime_sec());
  printVal(true, signal_flags());
  printVal(true, signal_unacked());
  Serial.println();
  return E_OK;
}

static uint8_t cmdRead(uint8_t n) {
  if (n != 1) return E_ARGS;
  if (sensor_state() == SENSOR_MISSING) return E_SENSOR;
  Serial.print(F("OK"));
  printValues();
  uint32_t now = millis();
  printVal(sensor_hasData(), (int32_t)sensor_ageSec(now));
  Serial.println();
  return E_OK;
}

static uint8_t findKey(const char *tok) {
  for (uint8_t k = 0; k < CFG_KEYS; k++) {
    if (is(tok, (const char *)pgm_read_ptr(&CFG_NAME[k]))) return k;
  }
  return 0xFF;
}

static uint8_t cmdCfg(char **t, uint8_t n) {
  if (n == 1) {
    sendOk();
    for (uint8_t k = 0; k < CFG_KEYS; k++) {
      Serial.print(F("C "));
      Serial.print(flashStr(CFG_NAME, k));
      int16_t v = storage_get(k);
      if (v == THR_OFF && storage_allowsOff(k)) {
        Serial.println(F(" OFF"));
      } else {
        printVal(true, v);
        Serial.println();
      }
    }
    Serial.println(F("END"));
    return E_OK;
  }
  if (is(t[1], K_RESET)) {
    if (n != 2) return E_ARGS;
    storage_resetConfig();
    sendOk();
    signal_evaluate(false);  // thresholds now OFF -> EVT ALARM ... 0 after the OK
    return E_OK;
  }
  uint8_t key = findKey(t[1]);
  if (key == 0xFF) return E_RANGE;  // unknown key
  if (n != 3) return E_ARGS;        // value missing
  int32_t v;
  if (is(t[2], K_OFF)) {
    if (!storage_allowsOff(key)) return E_ARGS;  // "OFF" is not a number for this key
    v = THR_OFF;
  } else {
    if (!parseInt(t[2], v)) return E_ARGS;
    if (v < -32767 || v > 32767) return E_RANGE;
  }
  if (!storage_set(key, (int16_t)v)) return E_RANGE;
  sendOk();
  signal_evaluate(false);  // a threshold switched OFF ends its alarm
  return E_OK;
}

static uint8_t cmdStream(char **t, uint8_t n) {
  bool on;
  if (!parseFlag(t, n, 1, on)) return E_ARGS;
  s_stream = on;
  sendOk();
  return E_OK;
}

static uint8_t cmdAck(uint8_t n) {
  if (n != 1) return E_ARGS;
  if (!signal_ack()) return E_STATE;
  sendOk();
  return E_OK;
}

static char *put2(char *p, uint8_t v) {
  *p++ = (char)('0' + v / 10);
  *p++ = (char)('0' + v % 10);
  return p;
}

// TIME [hh:mm:ss] - set / query the wall clock (RAM only).
static uint8_t cmdTime(char **t, uint8_t n, uint32_t now) {
  if (n == 1) {
    char buf[9];
    if (s_clockValid) {
      uint32_t s = s_clockSec;
      char *p = put2(buf, (uint8_t)(s / 3600));
      *p++ = ':';
      p = put2(p, (uint8_t)(s / 60 % 60));
      *p++ = ':';
      p = put2(p, (uint8_t)(s % 60));
      *p = '\0';
    } else {
      strcpy_P(buf, PSTR("--:--:--"));
    }
    Serial.print(F("OK "));
    Serial.println(buf);
    return E_OK;
  }
  if (n != 2) return E_ARGS;
  const char *a = t[1];
  if (strlen(a) != 8 || a[2] != ':' || a[5] != ':') return E_ARGS;
  uint8_t v[3];
  for (uint8_t i = 0; i < 3; i++) {
    char d1 = a[i * 3], d2 = a[i * 3 + 1];
    if (d1 < '0' || d1 > '9' || d2 < '0' || d2 > '9') return E_ARGS;
    v[i] = (uint8_t)((d1 - '0') * 10 + (d2 - '0'));
  }
  if (v[0] > 23 || v[1] > 59 || v[2] > 59) return E_ARGS;
  s_clockSec = (uint32_t)v[0] * 3600UL + v[1] * 60U + v[2];
  s_clockTick = now;
  s_clockValid = true;
  sendOk();
  return E_OK;
}

// Diagnostics: DEBUG TOUCH <0|1>, CAL SHOW, TESTPATTERN.
static uint8_t cmdDebug(char **t, uint8_t n) {
  if (n < 2) return E_ARGS;
  if (!is(t[1], K_TOUCH)) return E_UNKNOWN;
  bool on;
  if (!parseFlag(t, n, 2, on)) return E_ARGS;
  s_debugTouch = on;
  sendOk();
  return E_OK;
}

static uint8_t cmdCal(char **t, uint8_t n) {
  if (n < 2) return E_ARGS;
  if (!is(t[1], K_SHOW)) return E_UNKNOWN;
  if (n != 2) return E_ARGS;
  Serial.print(F("OK CAL"));
  printVal(true, g_cal.left);
  printVal(true, g_cal.right);
  printVal(true, g_cal.top);
  printVal(true, g_cal.bottom);
  printVal(true, g_cal.flags & CAL_FLAG_SWAP);
  printVal(true, (g_cal.flags & CAL_FLAG_USER) ? 1 : 0);
  Serial.println();
  return E_OK;
}

// ------------------------------------------------------------------ dispatcher
static void handleLine(uint32_t now) {
  char *tok[MAX_TOKENS + 1];
  uint8_t n = 0;
  char *p = s_line;
  while (*p != '\0') {
    while (*p == ' ') *p++ = '\0';
    if (*p == '\0') break;
    if (n <= MAX_TOKENS) {  // n == MAX_TOKENS + 1 means "too many" (-> ERR 2)
      tok[n] = p;
      n++;
    }
    while (*p != '\0' && *p != ' ') p++;
  }
  if (n == 0) return;  // empty line: ignored

  s_hadCmd = true;
  s_lastCmdMs = now;
  ui_testPatternEnd();  // any command leaves the test screen (no-op otherwise)

  uint8_t e;
  const char *c = tok[0];
  if (n > MAX_TOKENS) {
    e = E_ARGS;
  } else if (is(c, K_PING)) {
    e = E_ARGS;
    if (n == 1) {
      Serial.println(F("OK PONG " FW_NAME " " FW_VERSION));
      e = E_OK;
    }
  } else if (is(c, K_STATUS)) {
    e = cmdStatus(n);
  } else if (is(c, K_READ)) {
    e = cmdRead(n);
  } else if (is(c, K_CFG)) {
    e = cmdCfg(tok, n);
  } else if (is(c, K_STREAM)) {
    e = cmdStream(tok, n);
  } else if (is(c, K_ACK)) {
    e = cmdAck(n);
  } else if (is(c, K_TIME)) {
    e = cmdTime(tok, n, now);
  } else if (is(c, K_DEBUG)) {
    e = cmdDebug(tok, n);
  } else if (is(c, K_CAL)) {
    e = cmdCal(tok, n);
  } else if (is(c, K_TESTPATTERN)) {
    e = E_ARGS;
    if (n == 1) {
      sendOk();
      ui_testPatternBegin();
      e = E_OK;
    }
  } else {
    e = E_UNKNOWN;
  }
  if (e != E_OK) sendErr(e);
}

void protocol_begin() { Serial.begin(SERIAL_BAUD); }

void protocol_pump() {
  while (!s_ready && !s_inCmd && Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      s_line[s_len] = '\0';
      s_ready = true;
    } else if (s_len >= LINE_MAX) {
      s_overflow = true;  // discard the rest of the line
    } else if (!s_overflow) {
      s_line[s_len++] = ch;
    }
  }
}

void protocol_poll(uint32_t now) {
  clockUpdate(now);
  protocol_pump();
  if (!s_ready) return;  // at most one command per loop pass
  s_len = 0;
  s_inCmd = true;
  if (s_overflow) {
    s_hadCmd = true;
    s_lastCmdMs = now;
    sendErr(E_ARGS);  // line longer than LINE_MAX: discarded
  } else {
    handleLine(now);
  }
  s_overflow = false;
  s_ready = false;
  s_inCmd = false;
}

bool protocol_pcActive(uint32_t now) {
  return s_hadCmd && (uint32_t)(now - s_lastCmdMs) < PC_INDICATOR_MS;
}
