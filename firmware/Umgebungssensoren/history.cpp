#include "history.h"

#include "sensor.h"

static int16_t s_ring[HIST_VALUES][GRAPH_POINTS];
static uint8_t s_head = 0;  // next slot to write = oldest point
static uint8_t s_gen = 0;
static uint32_t s_lastMs = 0;
const uint8_t RING_MASK = GRAPH_POINTS - 1;
static_assert((GRAPH_POINTS & RING_MASK) == 0, "GRAPH_POINTS must be a power of two");
static_assert(VALID_T == 1 && VALID_RH == 2 && VALID_P == 4 && VALID_GAS == 8, "value order");

void history_begin() {  // empty graph = all gaps (never 0)
  int16_t *p = &s_ring[0][0];
  for (uint16_t i = 0; i < (uint16_t)HIST_VALUES * GRAPH_POINTS; i++) p[i] = GRAPH_GAP;
  s_lastMs = millis();
}

void history_poll(uint32_t now) {
  if ((uint32_t)(now - s_lastMs) < GRAPH_STEP_S * 1000UL) return;
  s_lastMs = now;
  // The latest measurement; its valid bits are 0 while the sensor is missing / before the
  // first measurement (sensor.cpp), so those points become gaps.
  const Measurement &m = sensor_data();
  uint32_t g = (m.gas + 50) / 100;  // 0.1 kOhm, clamped to the int16 range
  int16_t v[HIST_VALUES] = {(int16_t)((m.t + (m.t < 0 ? -5 : 5)) / 10), (int16_t)((m.rh + 5) / 10),
                            (int16_t)m.p, (int16_t)(g > 32767UL ? 32767UL : g)};
  uint8_t valid = m.valid;  // VALID_* bits in value order
  int16_t *slot = &s_ring[0][s_head];
  for (uint8_t k = 0; k < HIST_VALUES; k++, slot += GRAPH_POINTS, valid >>= 1) {
    *slot = (valid & 1) ? v[k] : GRAPH_GAP;
  }
  s_head = (uint8_t)((s_head + 1) & RING_MASK);
  s_gen++;
}

int16_t __attribute__((noinline)) history_get(uint8_t value, uint8_t i) { return s_ring[value][(uint8_t)(s_head + i) & RING_MASK]; }

uint8_t history_generation() { return s_gen; }
