#include "display.h"

#include <SPI.h>

#include "history.h"
#include "protocol.h"
#include "sensor.h"
#include "signal.h"

static Adafruit_ST7735 s_tft(PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);

void display_begin() {
  s_tft.initR(TFT_INIT_VARIANT);
  s_tft.setSPISpeed(TFT_SPI_HZ);
  s_tft.setRotation(TFT_ROTATION);
  s_tft.setTextWrap(false);
  s_tft.cp437(true);  // correct CP437 glyph mapping (umlauts, degree, arrows)
  s_tft.fillScreen(COL_BG);  // setup() only
}

Adafruit_ST7735 &display_tft() { return s_tft; }

// fillRect in stripes of ~1200 px (~4 ms) with a serial pump in between.
void display_fill(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t c) {
  int16_t rows = 1200 / w + 1;
  while (h > 0) {
    int16_t r = h < rows ? h : rows;
    s_tft.fillRect(x, y, w, r, c);
    y += r;
    h -= r;
    protocol_pump();
  }
}

void display_clearAll() { display_fill(0, 0, SCREEN_W, SCREEN_H, COL_BG); }

void display_text(int16_t x, int16_t y, uint8_t size, uint16_t fg, uint16_t bg, const char *s) {
  s_tft.setTextSize(size);
  s_tft.setTextColor(fg, bg);
  s_tft.setCursor(x, y);
  s_tft.print(s);
}

void display_center(int16_t cx, int16_t y, uint8_t size, uint16_t fg, uint16_t bg, const char *s) {
  display_text(cx - (int16_t)(strlen(s) * 3 * size), y, size, fg, bg, s);
}

void display_button(const Rect &r, const char *label_P, uint16_t face) {
  display_fill(r.x, r.y, r.w, r.h, face);
  s_tft.drawRect(r.x, r.y, r.w, r.h, COL_GREY);
  char buf[16];
  strncpy_P(buf, label_P, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';
  uint8_t len = strlen(buf);
  uint8_t size = (len * 12 <= r.w - 6 && r.h >= 26) ? 2 : 1;
  display_center(r.x + r.w / 2, r.y + (r.h - 8 * size) / 2, size, COL_FG, COL_FG, buf);
}

void display_fmtNum(char *out, uint8_t width, int32_t v, uint8_t dec) {
  char tmp[13];  // "-2147483648,0" worst case without the terminator: 12 chars
  char *p = tmp + sizeof(tmp) - 1;
  *p = '\0';
  uint32_t a = v < 0 ? 0UL - (uint32_t)v : (uint32_t)v;
  uint8_t n = 0;
  do {
    *--p = (char)('0' + a % 10);
    a /= 10;
    if (++n == dec) *--p = ',';
  } while (a != 0 || n <= dec);  // with a decimal: at least "0,d"
  if (v < 0) *--p = '-';
  uint8_t len = (uint8_t)(tmp + sizeof(tmp) - 1 - p);
  uint8_t pad = len < width ? width - len : 0;
  memset(out, ' ', pad);
  strcpy(out + pad, p);
}

// ------------------------------------------------------------------ overview
// Tiles: 0 temperature, 1 humidity (top row), 2 pressure, 3 gas (bottom row).
static const char L_T[] PROGMEM = "Temp. " DEG_ "C";
static const char L_RH[] PROGMEM = "Feuchte %";
static const char L_P[] PROGMEM = "Druck hPa";
static const char L_GAS[] PROGMEM = "Gas k" OHM_;
static const char *const TILE_LABEL[4] PROGMEM = {L_T, L_RH, L_P, L_GAS};

enum : uint8_t { V_NORMAL, V_ALARM, V_BLINK_ON, V_BLINK_OFF, V_NONE = 0xFF };

const uint8_t VAL_CHARS = 6;           // size 2: 72 px of the 80 px tile
static char s_val[4][VAL_CHARS + 1];   // value text on screen
static uint8_t s_vis[4];               // tile look on screen (V_*)
static uint8_t s_statusShown;          // text index * 4 + look
static uint16_t s_clockShown;          // minute of day, 0xFFFE = "--:--"
static bool s_pcShown;
static bool s_needFrame;

void display_overviewInvalidate() {
  for (uint8_t i = 0; i < 4; i++) {
    s_vis[i] = V_NONE;
    s_val[i][0] = '\0';
  }
  s_statusShown = 0xFF;
  s_clockShown = 0xFFFF;
  s_pcShown = false;
  s_needFrame = true;
}

static void tileRect(uint8_t i, Rect &r) {
  r.x = (i & 1) ? TILE_W : 0;
  r.y = TILE_Y + ((i & 2) ? TILE_H : 0);
  r.w = TILE_W;
  r.h = TILE_H;
}

// Alarm bits of a tile: T_HI/T_LO for temperature, RH_HI/RH_LO for humidity.
static uint8_t tileBits(uint8_t i) { return i == 0 ? (ALARM_T_HI | ALARM_T_LO) : i == 1 ? (ALARM_RH_HI | ALARM_RH_LO) : 0; }

static uint8_t look(uint8_t bits, bool blinkOn) {
  if (signal_unacked() & bits) return blinkOn ? V_BLINK_ON : V_BLINK_OFF;
  return (signal_flags() & bits) ? V_ALARM : V_NORMAL;
}

static int32_t round10(int32_t v) { return (v + (v < 0 ? -5 : 5)) / 10; }

static void tileValue(uint8_t i, char *out) {
  const Measurement &m = sensor_data();
  static const uint8_t VALID_BIT[4] = {VALID_T, VALID_RH, VALID_P, VALID_GAS};
  if (!(m.valid & VALID_BIT[i])) {
    strcpy_P(out, PSTR("    --"));
    return;
  }
  if (i == 0) {
    display_fmtNum(out, VAL_CHARS, round10(m.t), 1);
  } else if (i == 1) {
    display_fmtNum(out, VAL_CHARS, round10(m.rh), 1);
  } else if (i == 2) {
    display_fmtNum(out, VAL_CHARS, m.p, 1);
  } else {
    if (m.gas < 100000UL) {
      display_fmtNum(out, VAL_CHARS - 1, (int32_t)((m.gas + 50) / 100), 1);
    } else {
      uint32_t k = (m.gas + 500) / 1000;
      display_fmtNum(out, VAL_CHARS - 1, (int32_t)(k > 99999UL ? 99999UL : k), 0);
    }
    int8_t tr = sensor_gasTrend();
    out[VAL_CHARS - 1] = tr > 0 ? GLYPH_UP : tr < 0 ? GLYPH_DOWN : GLYPH_RIGHT;
    out[VAL_CHARS] = '\0';
  }
}

static void drawTile(uint8_t i, uint8_t vis, bool full) {
  Rect r;
  tileRect(i, r);
  uint16_t bg = vis == V_BLINK_ON ? COL_ALARM : COL_BG;
  uint16_t fg = (vis == V_ALARM || vis == V_BLINK_OFF) ? COL_ALARM : COL_FG;
  if (full) {
    display_fill(r.x, r.y, r.w, r.h, bg);
    s_tft.drawRect(r.x, r.y, r.w, r.h, COL_GREY);
    char buf[12];
    strcpy_P(buf, (const char *)pgm_read_ptr(&TILE_LABEL[i]));
    display_text(r.x + 4, r.y + 4, 1, bg == COL_BG ? COL_GREY : COL_FG, bg, buf);
    uint8_t f = signal_flags() & tileBits(i);
    if (f) {  // text, not only colour: which limit is violated
      strcpy_P(buf, (f & (ALARM_T_HI | ALARM_RH_HI)) ? PSTR("! zu hoch") : PSTR("! zu tief"));
      display_text(r.x + 4, r.y + 44, 1, fg, bg, buf);
    }
  }
  display_text(r.x + 4, r.y + 22, 2, fg, bg, s_val[i]);
}

static void drawStatus(uint8_t code) {
  static const char T0[] PROGMEM = "Sensor OK";
  static const char T1[] PROGMEM = "Sensor fehlt!";
  static const char T2[] PROGMEM = "Messfehler!";
  static const char T3[] PROGMEM = "Messung...";
  static const char *const TXT[4] PROGMEM = {T0, T1, T2, T3};
  uint8_t vis = code & 3;
  uint16_t bg = vis == V_BLINK_ON ? COL_ALARM : COL_BG;
  uint16_t fg = vis == V_NORMAL ? COL_GREY : (vis == V_BLINK_ON ? COL_FG : COL_ALARM);
  char buf[15];
  memset(buf, ' ', 14);
  buf[14] = '\0';
  char t[14];
  strcpy_P(t, (const char *)pgm_read_ptr(&TXT[code >> 2]));
  uint8_t len = strlen(t);
  memcpy(buf + (14 - len) / 2, t, len);  // centered in a fixed 14-char field
  display_text(36, 2, 1, fg, bg, buf);
}

void display_overviewUpdate(uint32_t now) {
  if (s_needFrame) {
    s_tft.drawFastHLine(0, STATUS_H - 1, SCREEN_W, COL_GREY);
    s_needFrame = false;
    return;
  }
  bool blinkOn = ((now / BLINK_MS) & 1) == 0;
  // clock "HH:MM" top left, redrawn only when the minute changes
  uint16_t minute = clock_valid() ? (uint16_t)(clock_secOfDay() / 60) : 0xFFFE;
  if (minute != s_clockShown) {
    s_clockShown = minute;
    char t[6];
    if (minute == 0xFFFE) {
      strcpy_P(t, PSTR("--:--"));
    } else {
      t[0] = (char)('0' + minute / 600);
      t[1] = (char)('0' + minute / 60 % 10);
      t[2] = ':';
      t[3] = (char)('0' + minute % 60 / 10);
      t[4] = (char)('0' + minute % 10);
      t[5] = '\0';
    }
    display_text(2, 2, 1, COL_FG, COL_BG, t);
  }
  bool pc = protocol_pcActive(now);
  if (pc != s_pcShown) {  // small "PC" mark top right
    s_pcShown = pc;
    char t[3] = {'P', 'C', '\0'};
    display_text(SCREEN_W - 14, 2, 1, pc ? COL_GREY : COL_BG, COL_BG, t);
  }
  uint8_t st = sensor_state();
  uint8_t txt = st == SENSOR_MISSING ? 1 : st == SENSOR_ERROR ? 2 : sensor_hasData() ? 0 : 3;
  uint8_t code = (uint8_t)(txt * 4 + look(ALARM_SENSOR, blinkOn));
  if (code != s_statusShown) {
    s_statusShown = code;
    drawStatus(code);
  }
  for (uint8_t i = 0; i < 4; i++) {
    uint8_t vis = look(tileBits(i), blinkOn);
    char v[VAL_CHARS + 1];
    tileValue(i, v);
    bool full = vis != s_vis[i];
    if (full || strcmp(v, s_val[i]) != 0) {
      strcpy(s_val[i], v);
      s_vis[i] = vis;
      drawTile(i, vis, full);
      return;  // at most one tile per pass
    }
  }
}

// The tiles fill the screen below TILE_Y in a 2 x 2 grid (same geometry as tileRect()).
uint8_t display_tileAt(int16_t x, int16_t y) {
  if (y < TILE_Y) return 0xFF;
  return (uint8_t)((x >= TILE_W ? 1 : 0) | (y >= TILE_Y + TILE_H ? 2 : 0));
}

// ------------------------------------------------------------------ history graph (PROJ-10)
// Title row: value name + time span; left column: axis max (top) / min (bottom); plot frame =
// GRAPH_X/Y/W/H (also the tap target GRAPH_AREA in ui.cpp). The plot is redrawn left to right in steps:
// each step clears the columns of one segment and draws it (no full clear, no flicker).
const int16_t PLOT_X = GRAPH_X + 1, PLOT_Y = GRAPH_Y + 1;
const int16_t PLOT_W = GRAPH_W - 2, PLOT_H = GRAPH_H - 2;

static uint8_t s_gValue = 0xFF;  // value whose title is on screen
static uint8_t s_gGen;            // history generation of the plot on screen
static uint8_t s_gSeg = GRAPH_POINTS;  // next segment to draw (GRAPH_POINTS = done)
static bool s_gDirty;             // plot must restart
static int16_t s_gLo, s_gHi;      // axis of the plot being drawn

void display_graphInvalidate() { s_gValue = 0xFF; }

static int16_t plotX(uint8_t i) { return PLOT_X + (int16_t)((uint16_t)i * (PLOT_W - 1) / (GRAPH_POINTS - 1)); }

static int16_t plotY(int16_t v) {
  return PLOT_Y + PLOT_H - 1 - (int16_t)((int32_t)(v - s_gLo) * (PLOT_H - 1) / (s_gHi - s_gLo));
}

static void graphLabel(int16_t y, int16_t v) {
  char buf[8];
  if (v == GRAPH_GAP) {
    strcpy_P(buf, PSTR("    --"));
  } else {
    display_fmtNum(buf, 6, v, 1);
  }
  display_text(0, y, 1, COL_FG, COL_BG, buf);
}

// Start a new plot: axis from the min/max of the valid points, labels.
static void graphStart(uint8_t value) {
  int16_t lo = 32767, hi = GRAPH_GAP;
  for (uint8_t i = 0; i < GRAPH_POINTS; i++) {
    int16_t v = history_get(value, i);
    if (v == GRAPH_GAP) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (hi == GRAPH_GAP) {
    lo = GRAPH_GAP;  // no data: labels "--", empty plot
  } else if (hi - lo < GRAPH_MIN_SPAN) {  // flat line: centre it on a minimum span
    lo -= (GRAPH_MIN_SPAN - (hi - lo)) / 2;
    hi = lo + GRAPH_MIN_SPAN;
  }
  s_gLo = lo;
  s_gHi = hi;
  graphLabel(GRAPH_Y, hi);
  graphLabel(GRAPH_Y + GRAPH_H - 8, lo);
  s_gSeg = 0;
}

void display_graphUpdate(uint8_t value) {
  if (value != s_gValue) {  // page entered or value switched: title, frame, new plot
    s_gValue = value;
    char buf[12];
    memset(buf, ' ', 11);
    buf[11] = '\0';
    strcpy_P(buf, (const char *)pgm_read_ptr(&TILE_LABEL[value]));
    buf[strlen(buf)] = ' ';  // fixed width: pads over a longer previous title
    display_text(2, 2, 1, COL_FG, COL_BG, buf);
    s_tft.print(GRAPH_POINTS * GRAPH_STEP_S / 60);  // time span of the ring
    s_tft.print(F(" min"));
    s_tft.drawRect(GRAPH_X, GRAPH_Y, GRAPH_W, GRAPH_H, COL_GREY);
    s_gDirty = true;
  }
  uint8_t gen = history_generation();
  if (gen != s_gGen) {  // new point (also while drawing): restart with the new data
    s_gGen = gen;
    s_gDirty = true;
  }
  if (s_gDirty) {
    s_gDirty = false;
    graphStart(value);
    return;
  }
  // One segment = the columns from point i (exclusive, except i = 0) to point i + 1: clear
  // them, then draw the line; a point next to a gap is drawn as a single pixel.
  for (uint8_t n = 0; n < GRAPH_SEG_PER_PASS && s_gSeg < GRAPH_POINTS; n++, s_gSeg++) {
    uint8_t i = s_gSeg;
    bool last = i == GRAPH_POINTS - 1;
    int16_t x0 = plotX(i), x1 = last ? x0 : plotX(i + 1);
    int16_t cx = i == 0 ? x0 : x0 + 1;
    s_tft.fillRect(cx, PLOT_Y, x1 - cx + 1, PLOT_H, COL_BG);  // width 0 for the last point
    int16_t a = history_get(value, i), b = last ? GRAPH_GAP : history_get(value, i + 1);
    if (a == GRAPH_GAP) continue;
    int16_t ya = plotY(a);
    if (b == GRAPH_GAP) {
      s_tft.drawPixel(x0, ya, COL_WARN);
    } else {
      s_tft.drawLine(x0, ya, x1, plotY(b), COL_WARN);
    }
  }
}
