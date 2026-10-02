#include "sensor.h"

#include <util/twi.h>

#include "storage.h"

// Minimal BME680 driver. Register map and integer compensation follow the Bosch BME680
// reference driver (bme680.c, integer variant); 64-bit arithmetic is replaced by exact
// 32-bit splits (flash). Forced mode, one heater set-point (GAS_HEATER_*).

// ------------------------------------------------------------------ registers
const uint8_t REG_RES_HEAT_VAL   = 0x00;
const uint8_t REG_RES_HEAT_RANGE = 0x02;  // bits 5:4
const uint8_t REG_RANGE_SW_ERR   = 0x04;  // bits 7:4 (signed)
const uint8_t REG_FIELD0         = 0x1D;  // status, meas index, P, T, H, gas (15 bytes)
const uint8_t FIELD_LEN          = 15;
const uint8_t REG_RES_HEAT0      = 0x5A;
const uint8_t REG_GAS_WAIT0      = 0x64;
const uint8_t REG_CTRL_GAS1      = 0x71;  // run_gas (bit 4), nb_conv 0
const uint8_t REG_CTRL_HUM       = 0x72;
const uint8_t REG_CTRL_MEAS      = 0x74;
const uint8_t REG_CONFIG         = 0x75;
const uint8_t REG_COEFF1         = 0x89;  // 25 bytes
const uint8_t REG_CHIP_ID        = 0xD0;
const uint8_t REG_RESET          = 0xE0;
const uint8_t REG_COEFF2         = 0xE1;  // 16 bytes
const uint8_t CHIP_ID            = 0x61;
const uint8_t CMD_SOFT_RESET     = 0xB6;
const uint8_t COEFF1_LEN = 25, COEFF2_LEN = 16;

const uint8_t STAT_NEW_DATA  = 0x80;  // field 0 status
const uint8_t GAS_VALID      = 0x20;  // gas_r_lsb
const uint8_t GAS_HEAT_STAB  = 0x10;
const uint8_t MODE_FORCED    = 0x01;
const uint8_t CTRL_MEAS_SLEEP = (uint8_t)((BME_OSRS_T << 5) | (BME_OSRS_P << 2));

// ------------------------------------------------------------------ state
struct Calib {
  uint16_t t1;
  int16_t t2;
  int8_t t3;
  uint16_t p1;
  int16_t p2;
  int8_t p3;
  int16_t p4, p5;
  int8_t p6, p7;
  int16_t p8, p9;
  uint8_t p10;
  uint16_t h1, h2;
  int8_t h3, h4, h5;
  uint8_t h6;
  int8_t h7;
  int8_t gh1;
  int16_t gh2;
  int8_t gh3;
  uint8_t heatRange;
  int8_t heatVal;
  int8_t swErr;
};

enum : uint8_t { ST_PROBE, ST_RESET_WAIT, ST_IDLE, ST_MEASURING };

static Calib s_cal;
static uint8_t s_st = ST_PROBE;
static uint8_t s_state = SENSOR_MISSING;
static uint8_t s_addr = 0;
static uint32_t s_t0 = 0;          // probe / reset / measurement start
static uint32_t s_lastPoll = 0;
static bool s_first = true;        // measure right away after (re)configuration
static bool s_probeNow = true;
static bool s_have = false;
static uint32_t s_measMs = 0;
static Measurement s_m;
static uint32_t s_gasAvg = 0;
static int8_t s_trend = 0;
static int8_t s_ambC = GAS_AMBIENT_DEFAULT_C;
static uint8_t s_gen = 0;

// ------------------------------------------------------------------ I2C (own TWI master)
// Polled TWI master instead of the Wire library (saves ~1.5 KB flash and ~200 B RAM).
// Every wait is bounded (I2C_SPIN_MAX): a stuck bus yields an error, never a hang.
static bool twiWait() {
  uint16_t n = I2C_SPIN_MAX;
  while (!(TWCR & _BV(TWINT))) {
    if (--n == 0) return false;
  }
  return true;
}

static void twiStop() {
  TWCR = _BV(TWINT) | _BV(TWEN) | _BV(TWSTO);
  uint16_t n = I2C_SPIN_MAX;
  while ((TWCR & _BV(TWSTO)) && --n != 0) {
  }
  if (n == 0) TWCR = _BV(TWEN);  // stop did not complete: reset the TWI unit
}

// (Repeated) start + address byte; true if the slave acknowledged.
static bool twiStart(uint8_t sla) {
  TWCR = _BV(TWINT) | _BV(TWSTA) | _BV(TWEN);
  if (!twiWait() || (TW_STATUS != TW_START && TW_STATUS != TW_REP_START)) return false;
  TWDR = sla;
  TWCR = _BV(TWINT) | _BV(TWEN);
  return twiWait() && TW_STATUS == ((sla & 1) ? TW_MR_SLA_ACK : TW_MT_SLA_ACK);
}

static bool twiWrite(uint8_t b) {
  TWDR = b;
  TWCR = _BV(TWINT) | _BV(TWEN);
  return twiWait() && TW_STATUS == TW_MT_DATA_ACK;
}

static bool wr(uint8_t reg, uint8_t val) {
  bool ok = twiStart((uint8_t)(s_addr << 1)) && twiWrite(reg) && twiWrite(val);
  twiStop();
  return ok;
}

static bool rd(uint8_t reg, uint8_t *buf, uint8_t n) {
  bool ok = twiStart((uint8_t)(s_addr << 1)) && twiWrite(reg) &&
            twiStart((uint8_t)((s_addr << 1) | 1));
  for (uint8_t i = 0; ok && i < n; i++) {
    TWCR = (uint8_t)(_BV(TWINT) | _BV(TWEN) | (i + 1 < n ? _BV(TWEA) : 0));  // NACK the last
    ok = twiWait();
    buf[i] = TWDR;
  }
  twiStop();
  return ok;
}

static uint16_t le16(const uint8_t *b, uint8_t lsb) { return (uint16_t)(b[lsb + 1] << 8) | b[lsb]; }

// ------------------------------------------------------------------ setup of the chip
static bool readCalib() {
  uint8_t c[COEFF1_LEN + COEFF2_LEN];
  uint8_t r[5];
  if (!rd(REG_COEFF1, c, COEFF1_LEN) || !rd(REG_COEFF2, c + COEFF1_LEN, COEFF2_LEN) ||
      !rd(REG_RES_HEAT_VAL, r, 5)) {
    return false;
  }
  s_cal.t1 = le16(c, 33);
  s_cal.t2 = (int16_t)le16(c, 1);
  s_cal.t3 = (int8_t)c[3];
  s_cal.p1 = le16(c, 5);
  s_cal.p2 = (int16_t)le16(c, 7);
  s_cal.p3 = (int8_t)c[9];
  s_cal.p4 = (int16_t)le16(c, 11);
  s_cal.p5 = (int16_t)le16(c, 13);
  s_cal.p7 = (int8_t)c[15];
  s_cal.p6 = (int8_t)c[16];
  s_cal.p8 = (int16_t)le16(c, 19);
  s_cal.p9 = (int16_t)le16(c, 21);
  s_cal.p10 = c[23];
  s_cal.h2 = (uint16_t)((uint16_t)c[25] << 4) | (c[26] >> 4);
  s_cal.h1 = (uint16_t)((uint16_t)c[27] << 4) | (c[26] & 0x0F);
  s_cal.h3 = (int8_t)c[28];
  s_cal.h4 = (int8_t)c[29];
  s_cal.h5 = (int8_t)c[30];
  s_cal.h6 = c[31];
  s_cal.h7 = (int8_t)c[32];
  s_cal.gh2 = (int16_t)le16(c, 35);
  s_cal.gh1 = (int8_t)c[37];
  s_cal.gh3 = (int8_t)c[38];
  s_cal.heatVal = (int8_t)r[REG_RES_HEAT_VAL];
  s_cal.heatRange = (uint8_t)((r[REG_RES_HEAT_RANGE] & 0x30) >> 4);
  s_cal.swErr = (int8_t)((int8_t)r[REG_RANGE_SW_ERR] & (int8_t)0xF0) / 16;
  // An all-zero/all-ones dump means a bus problem, not a chip.
  return s_cal.t1 != 0 && s_cal.t1 != 0xFFFF && s_cal.p1 != 0 && s_cal.p1 != 0xFFFF;
}

// Heater resistance code for GAS_HEATER_TEMP_C at the ambient temperature (Bosch).
static uint8_t heaterRes() {
  int32_t var1 = (((int32_t)s_ambC * s_cal.gh3) / 1000) * 256;
  int32_t var2 = ((int32_t)s_cal.gh1 + 784) *
                 (((((int32_t)s_cal.gh2 + 154009) * GAS_HEATER_TEMP_C * 5) / 100 + 3276800) / 10);
  int32_t var3 = var1 + var2 / 2;
  int32_t var4 = var3 / (s_cal.heatRange + 4);
  int32_t var5 = 131L * s_cal.heatVal + 65536L;
  int32_t x100 = (var4 / var5 - 250) * 34;
  return (uint8_t)((x100 + 50) / 100);
}

static uint8_t gasWaitCode() {
  uint8_t d = GAS_HEATER_MS, f = 0;
  while (d > 0x3F && f < 3) {
    d /= 4;
    f++;
  }
  return (uint8_t)(d + f * 64);
}

static bool configure() {
  return wr(REG_CTRL_HUM, BME_OSRS_H) && wr(REG_CONFIG, 0) && wr(REG_CTRL_MEAS, CTRL_MEAS_SLEEP) &&
         wr(REG_GAS_WAIT0, gasWaitCode()) && wr(REG_RES_HEAT0, heaterRes()) &&
         wr(REG_CTRL_GAS1, 0x10);
}

// ------------------------------------------------------------------ compensation (Bosch)
// (a * b) >> s for |a| < 2^17, |b| < 2^15, s = 11 without 32-bit overflow (exact floor).
static int32_t mulShr11(int32_t a, int32_t b) { return (a >> 11) * b + (((a & 0x7FF) * b) >> 11); }

static int32_t s_tFine;

static int16_t calcTemp(uint32_t adc) {
  int32_t var1 = (int32_t)(adc >> 3) - ((int32_t)s_cal.t1 << 1);
  int32_t var2 = mulShr11(var1, s_cal.t2);
  int32_t h = var1 >> 1;
  uint32_t ah = (uint32_t)(h < 0 ? -h : h);
  int32_t var3 = (int32_t)((ah * ah) >> 12);
  var3 = (var3 * ((int32_t)s_cal.t3 << 4)) >> 14;
  s_tFine = var2 + var3;
  return (int16_t)((s_tFine * 5 + 128) >> 8);
}

// Pa; 0 = invalid.
static uint32_t calcPress(uint32_t adc) {
  int32_t var1 = (s_tFine >> 1) - 64000;
  int32_t var2 = ((((var1 >> 2) * (var1 >> 2)) >> 11) * (int32_t)s_cal.p6) >> 2;
  var2 = var2 + ((var1 * (int32_t)s_cal.p5) << 1);
  var2 = (var2 >> 2) + ((int32_t)s_cal.p4 << 16);
  var1 = (((((var1 >> 2) * (var1 >> 2)) >> 13) * ((int32_t)s_cal.p3 << 5)) >> 3) +
         (((int32_t)s_cal.p2 * var1) >> 1);
  var1 = var1 >> 18;
  var1 = ((32768 + var1) * (int32_t)s_cal.p1) >> 15;
  if (var1 == 0) return 0;
  int32_t pc = 1048576L - (int32_t)adc;
  pc = (int32_t)((uint32_t)(pc - (var2 >> 12)) * 3125UL);
  if (pc >= 0x40000000L) {
    pc = (pc / var1) << 1;
  } else {
    pc = (pc << 1) / var1;
  }
  if (pc <= 0 || pc > 200000L) return 0;  // far outside P_MAX: skip (no overflow below)
  var1 = ((int32_t)s_cal.p9 * (int32_t)(((pc >> 3) * (pc >> 3)) >> 13)) >> 12;
  var2 = ((pc >> 2) * (int32_t)s_cal.p8) >> 13;
  uint32_t q = (uint32_t)(pc >> 8);
  uint32_t cube = q * q * q;  // pc < 2^17 here for any plausible pressure
  int32_t var3 = (int32_t)((cube >> 17) * s_cal.p10 + (((cube & 0x1FFFFUL) * s_cal.p10) >> 17));
  pc = pc + ((var1 + var2 + var3 + ((int32_t)s_cal.p7 << 7)) >> 4);
  return pc > 0 ? (uint32_t)pc : 0;
}

// 0.001 %rH
static int32_t calcHum(uint16_t adc) {
  int32_t ts = ((s_tFine * 5) + 128) >> 8;
  int32_t var1 = (int32_t)adc - ((int32_t)s_cal.h1 * 16) - (((ts * (int32_t)s_cal.h3) / 100) >> 1);
  int32_t var2 = ((int32_t)s_cal.h2 *
                  (((ts * (int32_t)s_cal.h4) / 100) +
                   (((ts * ((ts * (int32_t)s_cal.h5) / 100)) >> 6) / 100) + (1L << 14))) >> 10;
  int32_t var3 = var1 * var2;
  // Saturated readings: the terms below would overflow 32 bits (also in Bosch's int32
  // code); var3 > 6e8 is well above 100 %rH, var3 <= 0 at or below 0 %rH.
  if (var3 <= 0) return 0;
  if (var3 > 600000000L) return 100000L;
  int32_t var4 = ((((int32_t)s_cal.h6 << 7) + ((ts * (int32_t)s_cal.h7) / 100)) >> 4);
  int32_t var5 = ((var3 >> 14) * (var3 >> 14)) >> 10;
  int32_t var6 = (var4 * var5) >> 1;
  int32_t h = (((var3 + var6) >> 10) * 1000L) >> 12;
  if (h > 100000L) h = 100000L;
  if (h < 0) h = 0;
  return h;
}

static const uint32_t GAS_LUT1[16] PROGMEM = {
    2147483647UL, 2147483647UL, 2147483647UL, 2147483647UL, 2147483647UL, 2126008810UL,
    2147483647UL, 2130303777UL, 2147483647UL, 2147483647UL, 2143188679UL, 2136746228UL,
    2147483647UL, 2126008810UL, 2147483647UL, 2147483647UL};
static const uint32_t GAS_LUT2[16] PROGMEM = {
    4096000000UL, 2048000000UL, 1024000000UL, 512000000UL, 255744255UL, 127110228UL,
    64000000UL,   32258064UL,   16016016UL,   8000000UL,   4000000UL,   2000000UL,
    1000000UL,    500000UL,     250000UL,     125000UL};

// Ohm; 0 = invalid. Bosch: (lut2 * var1 >> 9 + var2 / 2) / var2 with a 64-bit numerator,
// done here as 32x32 -> 64 multiply and shift-subtract division.
static uint32_t calcGas(uint16_t adc, uint8_t range) {
  uint32_t lut1 = pgm_read_dword(&GAS_LUT1[range]);
  uint32_t f = (uint32_t)(1340 + 5 * (int16_t)s_cal.swErr);
  uint32_t var1 = f * (lut1 >> 16) + ((f * (lut1 & 0xFFFFUL)) >> 16);
  int32_t var2 = ((int32_t)adc << 15) - 16777216L + (int32_t)var1;
  if (var2 <= 0) return 0;
  uint32_t a = pgm_read_dword(&GAS_LUT2[range]), b = var1;
  // 64-bit product hi:lo
  uint32_t al = a & 0xFFFF, ah = a >> 16, bl = b & 0xFFFF, bh = b >> 16;
  uint32_t ll = al * bl, lh = al * bh, hl = ah * bl;
  uint32_t mid = (ll >> 16) + (lh & 0xFFFF) + (hl & 0xFFFF);
  uint32_t lo = (ll & 0xFFFF) | (mid << 16);
  uint32_t hi = ah * bh + (lh >> 16) + (hl >> 16) + (mid >> 16);
  // >> 9, + var2 / 2
  lo = (lo >> 9) | (hi << 23);
  hi >>= 9;
  uint32_t add = (uint32_t)var2 >> 1;
  lo += add;
  if (lo < add) hi++;
  uint32_t d = (uint32_t)var2;
  if (hi >= d) return 0xFFFFFFFFUL;  // quotient does not fit (practically impossible)
  uint32_t q = 0;
  for (uint8_t i = 0; i < 32; i++) {
    bool carry = (hi & 0x80000000UL) != 0;
    hi = (hi << 1) | (lo >> 31);
    lo <<= 1;
    q <<= 1;
    if (carry || hi >= d) {
      hi -= d;
      q |= 1;
    }
  }
  return q;
}

// ------------------------------------------------------------------ state handling
static uint8_t setState(uint8_t st) {
  if (st == s_state) return 0;
  s_state = st;
  s_gen++;
  return SENSOR_EV_STATE;
}

// I2C failure or chip gone: forget everything, probe again later.
static uint8_t lost(uint32_t now) {
  s_st = ST_PROBE;
  s_t0 = now;
  s_probeNow = false;
  s_have = false;
  s_m.valid = 0;
  s_trend = 0;
  s_gasAvg = 0;
  return setState(SENSOR_MISSING);
}

static bool probe(uint8_t addr) {
  s_addr = addr;
  uint8_t id = 0;
  return rd(REG_CHIP_ID, &id, 1) && id == CHIP_ID;
}

static void updateTrend(uint32_t gas) {
  if (s_gasAvg == 0) {
    s_gasAvg = gas;
    s_trend = 0;
    return;
  }
  uint32_t band = s_gasAvg / GAS_TREND_DIV;
  s_trend = gas > s_gasAvg + band ? 1 : (gas + band < s_gasAvg ? -1 : 0);
  int32_t diff = (int32_t)(gas - s_gasAvg);  // |diff| < 2^31 for any real resistance
  s_gasAvg = (uint32_t)((int32_t)s_gasAvg + (diff >> GAS_TREND_SHIFT));
}

// Evaluate one field-0 dump; returns the new sensor state.
static uint8_t evaluate(const uint8_t *b) {
  Measurement m;
  m.valid = 0;
  m.t = 0;
  m.rh = 0;
  m.p = 0;
  m.gas = 0;
  uint32_t adcP = ((uint32_t)b[2] << 12) | ((uint32_t)b[3] << 4) | (b[4] >> 4);
  uint32_t adcT = ((uint32_t)b[5] << 12) | ((uint32_t)b[6] << 4) | (b[7] >> 4);
  uint16_t adcH = (uint16_t)((uint16_t)b[8] << 8) | b[9];
  uint16_t adcG = (uint16_t)((uint16_t)b[13] << 2) | (b[14] >> 6);
  uint8_t range = b[14] & 0x0F;

  int16_t tc = calcTemp(adcT);  // also sets t_fine for P and H
  // P and H depend on t_fine: only with a physically possible temperature.
  if (tc >= T_MIN && tc <= T_MAX) {
    s_ambC = (int8_t)(tc / 100);
    int32_t t = (int32_t)tc + g_cfg.val[CFG_TEMP_OFFSET];
    if (t >= T_MIN && t <= T_MAX) {
      m.t = (int16_t)t;
      m.valid |= VALID_T;
    }
    uint32_t p = (calcPress(adcP) + 5) / 10;  // Pa -> 0.1 hPa
    if (p >= P_MIN && p <= P_MAX) {
      m.p = (uint16_t)p;
      m.valid |= VALID_P;
    }
    if (adcH != 0x8000) {  // 0x8000 = humidity channel skipped
      m.rh = (uint16_t)((calcHum(adcH) + 5) / 10);  // clamped to 0..100 % by Bosch
      m.valid |= VALID_RH;
    }
  }
  if ((b[14] & (GAS_VALID | GAS_HEAT_STAB)) == (GAS_VALID | GAS_HEAT_STAB)) {
    uint32_t g = calcGas(adcG, range);
    if (g > 0 && g != 0xFFFFFFFFUL) {
      m.gas = g;
      m.valid |= VALID_GAS;
    }
  }
  if (m.valid & VALID_GAS) {
    updateTrend(m.gas);
  } else {
    s_trend = 0;
  }
  s_m = m;
  // ERROR: one of T / RH / P missing (gas alone may be invalid while the heater settles).
  return (m.valid & (VALID_T | VALID_RH | VALID_P)) == (VALID_T | VALID_RH | VALID_P) ? SENSOR_OK
                                                                                     : SENSOR_ERROR;
}

static uint8_t finish(uint32_t now, uint8_t newState) {
  s_have = true;
  s_measMs = now;
  s_st = ST_IDLE;
  s_gen++;
  return (uint8_t)(SENSOR_EV_DATA | setState(newState));
}

// ------------------------------------------------------------------ public
void sensor_begin() {
  // TWI master on A4/A5 with the internal pull-ups enabled (as the Wire library does).
  digitalWrite(SDA, HIGH);
  digitalWrite(SCL, HIGH);
  TWSR = 0;  // prescaler 1
  TWBR = (uint8_t)((F_CPU / I2C_CLOCK_HZ - 16) / 2);
  TWCR = _BV(TWEN);
  s_m.valid = 0;
  s_probeNow = true;
  // Probe right away; the soft-reset wait may block here (setup() only), so the state is
  // final (OK or MISSING) before EVT BOOT and no state events are pending.
  sensor_poll(millis());
  if (s_st == ST_RESET_WAIT) {
    delay(SENSOR_RESET_MS);
    sensor_poll(millis());
  }
}

uint8_t sensor_poll(uint32_t now) {
  switch (s_st) {
    case ST_PROBE:
      if (!s_probeNow && (uint32_t)(now - s_t0) < SENSOR_RETRY_MS) return 0;
      s_probeNow = false;
      s_t0 = now;
      if (!probe(BME_ADDR_PRIMARY) && !probe(BME_ADDR_SECONDARY)) {
        s_addr = 0;
        return lost(now);
      }
      if (!wr(REG_RESET, CMD_SOFT_RESET)) return lost(now);
      s_st = ST_RESET_WAIT;
      return 0;

    case ST_RESET_WAIT:
      if ((uint32_t)(now - s_t0) < SENSOR_RESET_MS) return 0;
      if (!probe(s_addr) || !readCalib() || !configure()) {
        s_addr = 0;
        return lost(now);
      }
      s_st = ST_IDLE;
      s_first = true;
      return setState(SENSOR_OK);

    case ST_IDLE: {
      uint32_t interval = (uint32_t)g_cfg.val[CFG_INTERVAL] * 1000UL;
      if (!s_first && (uint32_t)(now - s_t0) < interval) return 0;
      s_first = false;
      s_t0 = now;
      s_lastPoll = now;
      // heater set-point follows the ambient temperature; then start one forced cycle
      if (!wr(REG_RES_HEAT0, heaterRes()) || !wr(REG_CTRL_MEAS, CTRL_MEAS_SLEEP | MODE_FORCED)) {
        return lost(now);
      }
      s_st = ST_MEASURING;
      return 0;
    }

    case ST_MEASURING:
    default: {
      if ((uint32_t)(now - s_t0) < SENSOR_MEAS_WAIT_MS) return 0;
      if ((uint32_t)(now - s_lastPoll) < SENSOR_POLL_MS) return 0;
      s_lastPoll = now;
      uint8_t b[FIELD_LEN];
      if (!rd(REG_FIELD0, b, FIELD_LEN)) return lost(now);
      if (!(b[0] & STAT_NEW_DATA)) {
        if ((uint32_t)(now - s_t0) < SENSOR_MEAS_TIMEOUT_MS) return 0;
        s_m.valid = 0;  // conversion never finished: no stale values
        s_trend = 0;
        return finish(now, SENSOR_ERROR);
      }
      return finish(now, evaluate(b));  // next cycle is timed from the trigger (s_t0)
    }
  }
}

uint8_t sensor_state() { return s_state; }
uint8_t sensor_address() { return s_state == SENSOR_MISSING ? 0 : s_addr; }
const Measurement &sensor_data() { return s_m; }
bool sensor_hasData() { return s_have; }
uint32_t sensor_ageSec(uint32_t now) { return (uint32_t)(now - s_measMs) / 1000UL; }
int8_t sensor_gasTrend() { return s_trend; }
uint8_t sensor_generation() { return s_gen; }
