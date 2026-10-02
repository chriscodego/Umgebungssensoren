// display - ST7735 (Adafruit GFX): drawing primitives and the overview page (status line +
// four value tiles) with dirty tracking. Never reads touch or Serial; long fills call
// protocol_pump() so serial input is not lost.
#pragma once

#include <Adafruit_ST7735.h>

#include "config.h"
#include "input.h"  // Rect

// Colours (RGB565)
const uint16_t COL_BG      = ST77XX_BLACK;
const uint16_t COL_FG      = ST77XX_WHITE;
const uint16_t COL_GREY    = 0x7BEF;
const uint16_t COL_ALARM   = ST77XX_RED;
const uint16_t COL_WARN    = ST77XX_YELLOW;
const uint16_t COL_BTN     = 0x2124;  // dark grey button face
const uint16_t COL_BTN_ON  = 0x033F;  // active tab / switched on (blue)
const uint16_t COL_BTN_NO  = 0x8000;  // dark red (destructive)

void display_begin();
Adafruit_ST7735 &display_tft();

void display_fill(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t c);  // striped + pump
void display_clearAll();

// Button: filled rect + border + centered label (PROGMEM); the same Rect is hit-tested.
void display_button(const Rect &r, const char *label_P, uint16_t face);
// Text with its left edge at x / centered on cx. bg == fg -> transparent.
void display_text(int16_t x, int16_t y, uint8_t size, uint16_t fg, uint16_t bg, const char *s);
void display_center(int16_t cx, int16_t y, uint8_t size, uint16_t fg, uint16_t bg, const char *s);
// Right-aligned decimal number with `dec` (0/1) decimals and a German comma, padded with
// spaces to `width` chars (out: width + 1 bytes).
void display_fmtNum(char *out, uint8_t width, int32_t v, uint8_t dec);

// ---- overview page: status line + 2 x 2 value tiles
void display_overviewInvalidate();         // full redraw (in steps) on the next updates
void display_overviewUpdate(uint32_t now); // redraw what changed (at most one tile per call)
uint8_t display_tileAt(int16_t x, int16_t y);  // tile index 0..3 under a tap, 0xFF = none

// ---- history graph page (PROJ-10): title, min/max labels, plot of history.* in steps
void display_graphInvalidate();            // title, frame and plot on the next updates
void display_graphUpdate(uint8_t value);   // redraw what changed (a few segments per call)
