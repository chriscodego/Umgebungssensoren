// ui - pages (overview, settings, touch calibration, history graph), hit-testing of taps.
// Drawing and hit-testing use the same rectangle tables.
#pragma once

#include "config.h"

void ui_begin(bool startCalibration);
void ui_update(uint32_t now);  // touch -> actions; redraw what is dirty
