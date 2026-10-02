// input - the ONLY module that knows the touch controller (XPT2046 on shared SPI).
// Pipeline: IRQ gate -> raw sample -> pressure/plausibility threshold -> debounce ->
// calibration (raw -> screen px) -> events TOUCH_DOWN (debounced press) and TOUCH_UP
// (release, mean position + duration). Hit-testing happens in ui.cpp via rectContains().
#pragma once

#include "config.h"

enum TouchEventType : uint8_t { TOUCH_NONE = 0, TOUCH_DOWN = 1, TOUCH_UP = 2 };

struct TouchEvent {
  uint8_t type;
  int16_t x, y;        // DOWN: first position; UP: mean over the press (for taps)
  int16_t rawX, rawY;  // raw values of x/y (calibration)
  uint16_t durMs;      // UP: press duration
};

struct Rect {
  int16_t x, y, w, h;
};

void input_begin();
// Poll the controller (rate-limited internally). Returns true with a DOWN or UP event.
bool input_poll(uint32_t now, TouchEvent &ev);
// Discard the current press; accept input only after a full release + lockout.
void input_suppress(uint32_t now);
// Instant "is something pressing right now" (used at boot to enter calibration).
bool input_pressedNow();
// Hit-test with TOUCH_HIT_PAD tolerance around the drawn rectangle.
bool rectContains(const Rect &r, int16_t x, int16_t y);

// Diagnostics (DEBUG TOUCH): last pen-down sample, incl. ones below the pressure threshold.
struct TouchDebug {
  int16_t rawX, rawY, z, x, y;
};
bool input_debugSample(TouchDebug &d);  // true once per new sample
