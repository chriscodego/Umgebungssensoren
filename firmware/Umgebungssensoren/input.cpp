#include "input.h"

#include <SPI.h>

#include "storage.h"

// Minimal XPT2046 driver (pattern from GloveboxControl FW 0.5.x): same command sequence
// and axis naming as the XPT2046_Touchscreen library with rotation 1, so the measured
// calibration defaults apply. No interrupt: the pen-down state is read from T_IRQ.

// Of three readings, the mean of the two closest ones.
static int16_t bestTwoAvg(int16_t a, int16_t b, int16_t c) {
  int16_t ab = abs(a - b), ac = abs(a - c), bc = abs(b - c);
  if (ab <= ac && ab <= bc) return (a + b) / 2;
  if (ac <= ab && ac <= bc) return (a + c) / 2;
  return (b + c) / 2;
}

// One conversion burst; ends with a power-down command that re-enables PENIRQ.
static void readRaw(int16_t &x, int16_t &y, int16_t &z) {
  int16_t d[6];
  SPI.beginTransaction(SPISettings(TOUCH_SPI_HZ, MSBFIRST, SPI_MODE0));
  digitalWrite(PIN_TOUCH_CS, LOW);
  SPI.transfer(0xB1);                             // Z1
  int16_t z1 = SPI.transfer16(0xC1) >> 3;         // Z2
  z = z1 + 4095 - (int16_t)(SPI.transfer16(0x91) >> 3);
  SPI.transfer16(0x91);                           // dummy X (first one is noisy)
  static const uint8_t CMD[6] = {0xD1, 0x91, 0xD1, 0x91, 0xD0, 0x00};
  for (uint8_t i = 0; i < 6; i++) d[i] = SPI.transfer16(CMD[i]) >> 3;
  digitalWrite(PIN_TOUCH_CS, HIGH);
  SPI.endTransaction();
  if (z < 0) z = 0;
  x = bestTwoAvg(d[0], d[2], d[4]);
  y = bestTwoAvg(d[1], d[3], d[5]);
}

enum : uint8_t { ST_IDLE, ST_PENDING, ST_DOWN, ST_RELEASING };

static uint8_t s_state = ST_IDLE;
static bool s_suppressed = false;
static uint32_t s_lockoutStart = 0;
static uint32_t s_lastPoll = 0;
static uint32_t s_downStart = 0;
static uint32_t s_releaseStart = 0;
static uint16_t s_sumX = 0, s_sumY = 0;  // <= 16 x 4050 fits
static uint8_t s_count = 0;
static int16_t s_z = 0;
static int16_t s_peakZ = 0;
// 2-sample delay line: a sample is only averaged once two newer ones exist, so the
// low-pressure samples right before lift-off are never committed.
static int16_t s_hx[2], s_hy[2];
static uint8_t s_hn = 0;
static int16_t s_lastRx, s_lastRy;
static uint32_t s_lastRearm = 0;

const uint8_t MAX_AVG_SAMPLES = 16;  // keeps the sums within uint16_t

static TouchDebug s_dbg;
static bool s_dbgNew = false;

static int16_t __attribute__((noinline)) mapAxis(int32_t raw, int16_t lo, int16_t hi, int16_t size) {
  int32_t span = (int32_t)hi - lo;
  if (span == 0) return 0;
  int32_t v = (raw - lo) * (size - 1) / span;
  if (v < 0) v = 0;
  if (v > size - 1) v = size - 1;
  return (int16_t)v;
}

static void mapPoint(int16_t rx, int16_t ry, int16_t &x, int16_t &y) {
  bool swap = g_cal.flags & CAL_FLAG_SWAP;
  x = mapAxis(swap ? ry : rx, g_cal.left, g_cal.right, SCREEN_W);
  y = mapAxis(swap ? rx : ry, g_cal.top, g_cal.bottom, SCREEN_H);
}

void input_begin() {
  // T_CS high before anything else talks on the bus.
  pinMode(PIN_TOUCH_CS, OUTPUT);
  digitalWrite(PIN_TOUCH_CS, HIGH);
  SPI.begin();
#if TOUCH_IRQ_PULLUP
  pinMode(PIN_TOUCH_IRQ, INPUT_PULLUP);
#else
  pinMode(PIN_TOUCH_IRQ, INPUT);
#endif
}

// One plausibility-checked sample. Returns false for "not pressed".
static bool sample(int16_t &rx, int16_t &ry) {
  s_z = 0;
  // Pen-down gate: without this a missing module (MISO floating) yields fake pressure.
  if (digitalRead(PIN_TOUCH_IRQ) != LOW) return false;
  int16_t px, py, pz;
  readRaw(px, py, pz);
  s_dbg.rawX = px;
  s_dbg.rawY = py;
  s_dbg.z = pz;
  mapPoint(px, py, s_dbg.x, s_dbg.y);
  s_dbgNew = true;
  if (pz < TOUCH_Z_MIN) return false;
  if (px < TOUCH_RAW_MIN || px > TOUCH_RAW_MAX || py < TOUCH_RAW_MIN || py > TOUCH_RAW_MAX) {
    return false;
  }
  rx = px;
  ry = py;
  s_z = pz;
  return true;
}

bool input_pressedNow() {
  int16_t x, y;
  return sample(x, y);
}

void input_suppress(uint32_t now) {
  s_suppressed = true;
  s_lockoutStart = now;
  s_state = ST_IDLE;
  s_count = 0;
  s_hn = 0;
}

bool input_debugSample(TouchDebug &d) {
  if (!s_dbgNew) return false;
  s_dbgNew = false;
  d = s_dbg;
  return true;
}

// Hit box = drawn rect + TOUCH_HIT_PAD; a rect near the glass edge extends to the edge.
bool rectContains(const Rect &r, int16_t x, int16_t y) {
  int16_t x0 = (r.x <= TOUCH_EDGE_SNAP) ? 0 : r.x - TOUCH_HIT_PAD;
  int16_t y0 = (r.y <= TOUCH_EDGE_SNAP) ? 0 : r.y - TOUCH_HIT_PAD;
  int16_t x1 = (r.x + r.w >= SCREEN_W - TOUCH_EDGE_SNAP) ? SCREEN_W : r.x + r.w + TOUCH_HIT_PAD;
  int16_t y1 = (r.y + r.h >= SCREEN_H - TOUCH_EDGE_SNAP) ? SCREEN_H : r.y + r.h + TOUCH_HIT_PAD;
  return x >= x0 && x < x1 && y >= y0 && y < y1;
}

static void accumulate(int16_t rx, int16_t ry) {
  if (s_hn == 2) {  // commit the oldest buffered sample
    s_lastRx = s_hx[0];
    s_lastRy = s_hy[0];
    if (s_count < MAX_AVG_SAMPLES) {
      s_sumX += s_hx[0];
      s_sumY += s_hy[0];
      s_count++;
    }
    s_hx[0] = s_hx[1];
    s_hy[0] = s_hy[1];
    s_hn = 1;
  }
  s_hx[s_hn] = rx;
  s_hy[s_hn] = ry;
  s_hn++;
}

bool input_poll(uint32_t now, TouchEvent &ev) {
  if ((uint32_t)(now - s_lastPoll) < TOUCH_POLL_MS) return false;
  s_lastPoll = now;

  int16_t rx = 0, ry = 0;
  bool pressed = sample(rx, ry);
  // Idle: periodically re-arm PENIRQ so a glitched controller cannot leave touch dead.
  if (!pressed && s_state == ST_IDLE && (uint32_t)(now - s_lastRearm) >= TOUCH_REARM_MS) {
    s_lastRearm = now;
    int16_t a, b, c;
    readRaw(a, b, c);
  }
  // Within a press, samples below half the peak pressure count as "lifted".
  if (pressed && s_state != ST_IDLE) {
    if (s_z > s_peakZ) s_peakZ = s_z;
    if (s_z < s_peakZ / TOUCH_Z_PEAK_DIV) pressed = false;
  }

  if (s_suppressed) {
    // Wait for a full release, then the lockout time.
    if (pressed) {
      s_lockoutStart = now;
      return false;
    }
    if ((uint32_t)(now - s_lockoutStart) < TOUCH_LOCKOUT_MS) return false;
    s_suppressed = false;
    s_state = ST_IDLE;
  }

  switch (s_state) {
    case ST_IDLE:
      if (pressed) {
        s_state = ST_PENDING;
        s_downStart = now;
        s_sumX = s_sumY = 0;
        s_count = 0;
        s_hn = 0;
        s_peakZ = s_z;
      }
      return false;

    case ST_PENDING:
      if (!pressed) {
        s_state = ST_IDLE;  // bounce / noise shorter than the debounce time
        return false;
      }
      accumulate(rx, ry);
      if ((uint32_t)(now - s_downStart) < TOUCH_DEBOUNCE_MS) return false;
      s_state = ST_DOWN;
      if (s_count == 0) {
        s_lastRx = s_hx[0];
        s_lastRy = s_hy[0];
      }
      ev.type = TOUCH_DOWN;
      ev.rawX = s_lastRx;
      ev.rawY = s_lastRy;
      mapPoint(ev.rawX, ev.rawY, ev.x, ev.y);
      return true;

    case ST_DOWN:
      if (pressed) {
        accumulate(rx, ry);
      } else {
        s_state = ST_RELEASING;
        s_releaseStart = now;
        if (s_count == 0 && s_hn > 0) {
          s_sumX = s_hx[0];
          s_sumY = s_hy[0];
          s_count = 1;
        }
        s_hn = 0;
      }
      return false;

    case ST_RELEASING:
    default:
      if (pressed) {  // short drop-out: still the same press
        s_state = ST_DOWN;
        accumulate(rx, ry);
        return false;
      }
      if ((uint32_t)(now - s_releaseStart) < TOUCH_RELEASE_MS) return false;
      s_state = ST_IDLE;
      if (s_count == 0) return false;
      ev.rawX = (int16_t)(s_sumX / s_count);
      ev.rawY = (int16_t)(s_sumY / s_count);
      mapPoint(ev.rawX, ev.rawY, ev.x, ev.y);
      {
        uint32_t d = s_releaseStart - s_downStart;
        ev.durMs = d > 65535UL ? 65535U : (uint16_t)d;
      }
      ev.type = TOUCH_UP;
      return true;
  }
}
