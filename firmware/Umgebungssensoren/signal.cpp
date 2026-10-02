#include "signal.h"

#include <avr/interrupt.h>

#include "protocol.h"
#include "sensor.h"
#include "storage.h"

// ------------------------------------------------------------------ alarm logic
static uint8_t s_flags = 0;
static uint8_t s_unacked = 0;
static uint8_t s_count[4];  // consecutive violating measurements per threshold

static void setFlag(uint8_t bit, bool on) {
  if (((s_flags & bit) != 0) == on) return;
  if (on) {
    s_flags |= bit;
    s_unacked |= bit;
  } else {
    s_flags &= (uint8_t)~bit;
    s_unacked &= (uint8_t)~bit;
  }
  protocol_evtAlarm(bit, on);
}

// Thresholds in flag order: T_HI (1), T_LO (2), RH_HI (4), RH_LO (8).
void signal_evaluate(bool newData) {
  setFlag(ALARM_SENSOR, sensor_state() != SENSOR_OK);  // "no data" is an alarm, never "ok"
  const Measurement &m = sensor_data();
  for (uint8_t i = 0; i < 4; i++) {
    uint8_t bit = (uint8_t)(1u << i);
    int16_t thr = g_cfg.val[CFG_T_HI + i];
    if (thr == THR_OFF) {
      s_count[i] = 0;
      setFlag(bit, false);
      continue;
    }
    if (!newData) continue;
    bool isT = i < 2;
    if (!(m.valid & (isT ? VALID_T : VALID_RH))) {
      s_count[i] = 0;  // no value: keep the flag as it is (sensor alarm covers it)
      continue;
    }
    int16_t v = isT ? m.t : (int16_t)m.rh;
    int16_t hyst = isT ? ALARM_T_HYST : ALARM_RH_HYST;
    bool high = (i & 1) == 0;
    bool beyond = high ? v > thr : v < thr;
    bool backIn = high ? v <= thr - hyst : v >= thr + hyst;
    if (beyond) {
      if (s_count[i] < ALARM_SET_COUNT) s_count[i]++;
      if (s_count[i] >= ALARM_SET_COUNT) setFlag(bit, true);
    } else {
      s_count[i] = 0;
      if (backIn) setFlag(bit, false);
    }
  }
}

uint8_t signal_flags() { return s_flags; }
uint8_t signal_unacked() { return s_unacked; }

bool signal_ack() {
  if (s_unacked == 0) return false;
  s_unacked = 0;
  return true;
}

// ------------------------------------------------------------------ buzzer (Timer2)
// Timer2 in CTC mode, prescaler 32; the compare ISR toggles the piezo pin.
const uint8_t BUZZER_OCR = (uint8_t)(F_CPU / 32UL / (2UL * BUZZER_FREQ_HZ) - 1);
static_assert(F_CPU / 32UL / (2UL * BUZZER_FREQ_HZ) - 1 <= 255, "buzzer frequency too low");

static volatile uint8_t *s_pinReg;  // writing the bit mask to PINx toggles the pin
static uint8_t s_mask;
static uint8_t s_beepsLeft = 0;
static bool s_on = false;
static uint32_t s_nextMs = 0;       // next tone edge
static uint32_t s_burstMs = 0;      // start of the last burst
static bool s_burstDone = false;    // a burst ran for the current unacked alarm

ISR(TIMER2_COMPA_vect) { *s_pinReg = s_mask; }

static void piezo(bool on) {
  s_on = on;
  if (on) {
    TCCR2A = _BV(WGM21);
    OCR2A = BUZZER_OCR;
    TCNT2 = 0;
    TIMSK2 = _BV(OCIE2A);
    TCCR2B = _BV(CS21) | _BV(CS20);  // clk/32 -> starts the timer
  } else {
    TCCR2B = 0;
    TIMSK2 = 0;
    digitalWrite(PIN_BUZZER, LOW);
  }
}

void signal_begin() {
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  s_pinReg = portInputRegister(digitalPinToPort(PIN_BUZZER));
  s_mask = digitalPinToBitMask(PIN_BUZZER);
}

// Unacknowledged alarm + BUZZER 1: burst of BUZZER_BEEPS tones, repeated every
// BUZZER_REPEAT_MS. Acknowledging or switching the buzzer off stops it at once.
void signal_update(uint32_t now) {
  bool want = s_unacked != 0 && g_cfg.buzzer;
  if (!want) {
    if (s_on) piezo(false);
    s_beepsLeft = 0;
    s_burstDone = false;
    return;
  }
  if (s_beepsLeft == 0 && !s_on) {
    if (s_burstDone && (uint32_t)(now - s_burstMs) < BUZZER_REPEAT_MS) return;
    s_burstDone = true;
    s_burstMs = now;
    s_beepsLeft = BUZZER_BEEPS;
    s_nextMs = now;
  }
  if ((int32_t)(now - s_nextMs) < 0) return;  // overflow-safe "not yet"
  if (s_on) {
    piezo(false);
    s_nextMs = now + BUZZER_GAP_MS;
  } else if (s_beepsLeft > 0) {
    piezo(true);
    s_beepsLeft--;
    s_nextMs = now + BUZZER_BEEP_MS;
  }
}
