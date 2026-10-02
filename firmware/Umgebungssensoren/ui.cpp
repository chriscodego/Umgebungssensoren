#include "ui.h"

#include "display.h"
#include "input.h"
#include "protocol.h"
#include "signal.h"
#include "storage.h"

// Pages (SPEC "Anzeige"): overview (values), settings, touch calibration.
enum Page : uint8_t { PAGE_OVERVIEW, PAGE_SETTINGS, PAGE_CAL };

// ------------------------------------------------------------------ button tables (flash)
struct Button {
  Rect r;
  const char *label;  // PROGMEM
};

static const char L_BACK[] PROGMEM = "Zur" UE_ "ck";
static const char L_MINUS[] PROGMEM = "-";
static const char L_PLUS[] PROGMEM = "+";
static const char L_BUZ_ON[] PROGMEM = "Piezo: an";
static const char L_BUZ_OFF[] PROGMEM = "Piezo: aus";
static const char L_CAL[] PROGMEM = "Kalibrieren";
static const char L_DEFAULT[] PROGMEM = "Standard";
static const char L_SURE[] PROGMEM = "Sicher?";

// Settings: back button at the bottom.
static const Button BTN_BACK[] PROGMEM = {
    {{2, BACK_Y, 156, BACK_H}, L_BACK},
};

enum { B_MINUS = 0, B_PLUS, B_BUZZER, B_CAL, B_DEFAULT, B_SET_COUNT };
static const Button BTN_SET[] PROGMEM = {
    {{2, 14, 40, 28}, L_MINUS},
    {{118, 14, 40, 28}, L_PLUS},
    {{2, 46, 156, 26}, L_BUZ_OFF},  // label follows the setting
    {{2, 76, 77, 26}, L_CAL},
    {{81, 76, 77, 26}, L_DEFAULT},  // "Sicher?" while waiting for the confirming tap
};

// Overview: a tap on the top strip (clock/status) acknowledges an alarm and opens the settings;
// a tap on a value tile only acknowledges.
static const Rect TOP_AREA = {0, 0, SCREEN_W, SETTINGS_TAP_H};

static void drawButton(const Button *table, uint8_t i, const char *label_P, uint16_t face) {
  Button b;
  memcpy_P(&b, &table[i], sizeof(Button));
  display_button(b.r, label_P != nullptr ? label_P : b.label, face);
}

// Index of the button hit, or 0xFF.
static uint8_t hitButton(const Button *table, uint8_t n, int16_t x, int16_t y) {
  for (uint8_t i = 0; i < n; i++) {
    Button b;
    memcpy_P(&b, &table[i], sizeof(Button));
    if (rectContains(b.r, x, y)) return i;
  }
  return 0xFF;
}

// ------------------------------------------------------------------ state
static uint8_t s_page = PAGE_OVERVIEW;
static uint8_t s_returnPage = PAGE_OVERVIEW;  // after calibration
static uint8_t s_drawStep = 0;
const uint8_t DRAW_DONE = 0xFF;
static uint32_t s_lastActivity = 0;
static bool s_testPattern = false;

// settings page: values on screen (0x7FFF / 0xFF = redraw)
static int16_t s_shownInterval;
static uint8_t s_shownBuzzer;
static uint8_t s_shownConfirm;
static bool s_confirm = false;
static uint32_t s_confirmMs = 0;

// calibration
static uint8_t s_calStep = 0;
static bool s_calError = false;
static int16_t s_calRawX[4], s_calRawY[4];

static void drawBack() { drawButton(BTN_BACK, 0, nullptr, COL_BTN); }

// ------------------------------------------------------------------ settings page
static void drawInterval(int16_t v) {
  char num[6], buf[8];
  display_fmtNum(num, 0, v, 0);
  strcpy(buf, num);
  strcat_P(buf, PSTR(" s"));
  char field[7];  // centered in a fixed 6-char field (no stale digits)
  memset(field, ' ', 6);
  field[6] = '\0';
  uint8_t len = strlen(buf);
  if (len > 6) len = 6;
  memcpy(field + (6 - len) / 2, buf, len);
  display_text(SCREEN_W / 2 - 36, 20, 2, COL_FG, COL_BG, field);
}

static bool drawSettingsStep(uint8_t step) {
  if (step == 0) {
    display_clearAll();
    return false;
  }
  if (step == 1) {
    drawBack();
    return false;
  }
  if (step == 2) {
    char title[14];
    strcpy_P(title, PSTR("Messintervall"));
    display_center(SCREEN_W / 2, 3, 1, COL_GREY, COL_BG, title);
    drawButton(BTN_SET, B_MINUS, nullptr, COL_BTN);
    drawButton(BTN_SET, B_PLUS, nullptr, COL_BTN);
    return false;
  }
  drawButton(BTN_SET, B_CAL, nullptr, COL_BTN);
  s_shownInterval = 0x7FFF;  // dynamic parts follow in settingsRefresh()
  s_shownBuzzer = 0xFF;
  s_shownConfirm = 0xFF;
  return true;
}

// One changed element per call.
static void settingsRefresh(uint32_t now) {
  if (s_confirm && (uint32_t)(now - s_confirmMs) >= CONFIRM_MS) s_confirm = false;
  int16_t iv = g_cfg.val[CFG_INTERVAL];
  if (iv != s_shownInterval) {
    s_shownInterval = iv;
    drawInterval(iv);
    return;
  }
  if (g_cfg.buzzer != s_shownBuzzer) {
    s_shownBuzzer = g_cfg.buzzer;
    drawButton(BTN_SET, B_BUZZER, g_cfg.buzzer ? L_BUZ_ON : L_BUZ_OFF, g_cfg.buzzer ? COL_BTN_ON : COL_BTN);
    return;
  }
  uint8_t confirm = s_confirm ? 1 : 0;
  if (confirm != s_shownConfirm) {
    s_shownConfirm = confirm;
    drawButton(BTN_SET, B_DEFAULT, s_confirm ? L_SURE : L_DEFAULT, s_confirm ? COL_BTN_NO : COL_BTN);
  }
}

// Next interval step below (dir < 0) / above (dir > 0) the current value.
static int16_t stepInterval(int16_t cur, int8_t dir) {
  int16_t best = cur;
  for (uint8_t i = 0; i < INTERVAL_STEP_COUNT; i++) {
    int16_t s = (int16_t)pgm_read_word(&INTERVAL_STEPS[i]);
    if (dir < 0 && s < cur) best = s;  // ascending table: last smaller one
    if (dir > 0 && s > cur) return s;  // first larger one
  }
  return best;
}

static void enter(uint8_t page, uint32_t now);

static void onSettings(const TouchEvent &ev, uint32_t now) {
  uint8_t b = hitButton(BTN_SET, B_SET_COUNT, ev.x, ev.y);
  if (b != B_DEFAULT) s_confirm = false;
  switch (b) {
    case B_MINUS:
    case B_PLUS:
      storage_set(CFG_INTERVAL, stepInterval(g_cfg.val[CFG_INTERVAL], b == B_MINUS ? -1 : 1));
      break;
    case B_BUZZER:
      storage_set(CFG_BUZZER, g_cfg.buzzer ? 0 : 1);
      break;
    case B_CAL:
      s_returnPage = PAGE_SETTINGS;
      s_calError = false;
      enter(PAGE_CAL, now);
      return;
    case B_DEFAULT:
      if (s_confirm) {  // second tap within CONFIRM_MS: defaults (calibration is kept)
        s_confirm = false;
        storage_resetConfig();
        signal_evaluate(false);
      } else {
        s_confirm = true;
        s_confirmMs = now;
      }
      break;
    default:
      return;
  }
  input_suppress(now);  // one action per tap
}

// ------------------------------------------------------------------ calibration
static void calPoint(uint8_t step, int16_t &x, int16_t &y) {
  x = (step == 1 || step == 2) ? SCREEN_W - 1 - CAL_MARGIN : CAL_MARGIN;
  y = (step >= 2) ? SCREEN_H - 1 - CAL_MARGIN : CAL_MARGIN;
}

static void crossAt(int16_t x, int16_t y, uint16_t col) {
  Adafruit_ST7735 &tft = display_tft();
  tft.drawFastHLine(x - 8, y, 17, col);
  tft.drawFastVLine(x, y - 8, 17, col);
}

static void drawCross(uint8_t step, uint16_t col) {
  int16_t x, y;
  calPoint(step, x, y);
  crossAt(x, y, col);
}

static void drawCalText() {
  char line[20];
  strcpy_P(line, PSTR("Kreuz 1/4 dr" UE_ "cken"));
  line[6] = (char)('1' + s_calStep);
  display_center(SCREEN_W / 2, 60, 1, COL_FG, COL_BG, line);
  if (s_calError) {
    strcpy_P(line, PSTR("Fehler - nochmal"));
    display_center(SCREEN_W / 2, 76, 1, COL_ALARM, COL_BG, line);
  }
}

static bool drawCalStep(uint8_t step) {
  if (step == 0) {
    display_clearAll();
    return false;
  }
  drawCross(s_calStep, COL_ALARM);
  drawCalText();
  return true;
}

static bool finishCalibration() {
  // Which raw axis changes along the top edge (P0 -> P1) drives screen X?
  int16_t dx = abs(s_calRawX[1] - s_calRawX[0]);
  int16_t dy = abs(s_calRawY[1] - s_calRawY[0]);
  uint8_t swap = dy > dx ? 1 : 0;
  int16_t a[4], b[4];
  for (uint8_t i = 0; i < 4; i++) {
    a[i] = swap ? s_calRawY[i] : s_calRawX[i];
    b[i] = swap ? s_calRawX[i] : s_calRawY[i];
  }
  // Both edges must agree on the direction of each axis (inverted axes are fine).
  if (((a[1] - a[0]) > 0) != ((a[2] - a[3]) > 0)) return false;
  if (((b[3] - b[0]) > 0) != ((b[2] - b[1]) > 0)) return false;
  // Edges must be level/plumb: along each edge the cross axis moves < 1/4 of the span.
  int16_t spanA = abs(a[1] - a[0]) / 4, spanB = abs(b[3] - b[0]) / 4;
  if (abs(b[1] - b[0]) > spanB || abs(b[2] - b[3]) > spanB) return false;
  if (abs(a[3] - a[0]) > spanA || abs(a[2] - a[1]) > spanA) return false;
  int32_t aL = ((int32_t)a[0] + a[3]) / 2, aR = ((int32_t)a[1] + a[2]) / 2;
  int32_t bT = ((int32_t)b[0] + b[1]) / 2, bB = ((int32_t)b[2] + b[3]) / 2;
  // Extrapolate from the crosshair positions to the screen edges.
  const int32_t spanX = SCREEN_W - 1 - 2 * CAL_MARGIN;
  const int32_t spanY = SCREEN_H - 1 - 2 * CAL_MARGIN;
  TouchCal c;
  c.flags = (uint8_t)((swap ? CAL_FLAG_SWAP : 0) | CAL_FLAG_USER);
  c.left = (int16_t)(aL - (aR - aL) * CAL_MARGIN / spanX);
  c.right = (int16_t)(aR + (aR - aL) * CAL_MARGIN / spanX);
  c.top = (int16_t)(bT - (bB - bT) * CAL_MARGIN / spanY);
  c.bottom = (int16_t)(bB + (bB - bT) * CAL_MARGIN / spanY);
  if (!storage_calValid(c)) return false;
  g_cal = c;
  storage_saveCal();
  return true;
}

static void onCalibration(const TouchEvent &ev, uint32_t now) {
  s_calRawX[s_calStep] = ev.rawX;
  s_calRawY[s_calStep] = ev.rawY;
  drawCross(s_calStep, COL_BG);
  if (s_calStep < 3) {
    s_calStep++;
    drawCross(s_calStep, COL_ALARM);
    drawCalText();
    input_suppress(now);
    return;
  }
  s_calError = !finishCalibration();
  enter(s_calError ? (uint8_t)PAGE_CAL : s_returnPage, now);
}

// ------------------------------------------------------------------ transitions
static void enter(uint8_t page, uint32_t now) {
  s_page = page;
  s_lastActivity = now;
  s_drawStep = 0;
  s_confirm = false;
  input_suppress(now);  // a finger still on the glass must not hit the new page
  if (page == PAGE_CAL) s_calStep = 0;
}

static void drawPending() {
  if (s_drawStep == DRAW_DONE) return;
  bool done;
  if (s_page == PAGE_CAL) {
    done = drawCalStep(s_drawStep);
  } else if (s_page == PAGE_SETTINGS) {
    done = drawSettingsStep(s_drawStep);
  } else {  // overview: clear, then display_overviewUpdate() draws the rest
    if (s_drawStep == 0) {
      display_clearAll();
      done = false;
    } else {
      display_overviewInvalidate();
      done = true;
    }
  }
  s_drawStep = done ? DRAW_DONE : (uint8_t)(s_drawStep + 1);
}

void ui_begin(bool startCalibration) {
  s_calError = false;
  s_returnPage = PAGE_OVERVIEW;
  enter(startCalibration ? PAGE_CAL : PAGE_OVERVIEW, millis());
}

// ------------------------------------------------------------------ test pattern
static void testCross(int16_t x, int16_t y, char id) {
  Adafruit_ST7735 &tft = display_tft();
  crossAt(x, y, COL_ALARM);
  int16_t lx = (x > SCREEN_W / 2) ? x - 4 - 54 : x + 4;
  int16_t ly = (y > SCREEN_H / 2) ? y - 12 : y + 4;
  tft.setTextSize(1);
  tft.setTextColor(COL_FG);
  tft.setCursor(lx, ly);
  tft.print(id);
  tft.print(' ');
  tft.print(x);
  tft.print(',');
  tft.print(y);
}

void ui_testPatternBegin() {
  s_testPattern = true;
  display_clearAll();
  const int16_t l = TEST_INSET, r = SCREEN_W - 1 - TEST_INSET;
  const int16_t t = TEST_INSET, b = SCREEN_H - 1 - TEST_INSET;
  testCross(l, t, 'A');
  testCross(r, t, 'B');
  testCross(r, b, 'C');
  testCross(l, b, 'D');
  testCross(SCREEN_W / 2, SCREEN_H / 2, 'E');
}

void ui_testPatternEnd() {
  if (!s_testPattern) return;
  s_testPattern = false;
  enter(s_page == PAGE_CAL ? (uint8_t)PAGE_OVERVIEW : s_page, millis());
}

// ------------------------------------------------------------------ main update
void ui_update(uint32_t now) {
  TouchEvent ev = {TOUCH_NONE, 0, 0, 0, 0, 0};
  bool got = input_poll(now, ev);
  bool up = got && ev.type == TOUCH_UP;
  if (got) s_lastActivity = now;
  if (s_testPattern) return;  // static diagnostic screen: no actions, no redraws

  if (s_page == PAGE_CAL) {
    if (up) {
      onCalibration(ev, now);
    } else if ((uint32_t)(now - s_lastActivity) >= CAL_IDLE_TIMEOUT_MS) {
      s_calError = false;
      enter(s_returnPage, now);  // abort, keep the old calibration
    }
    drawPending();
    return;
  }

  if (up && s_drawStep == DRAW_DONE) {
    if (s_page == PAGE_SETTINGS) {
      if (hitButton(BTN_BACK, 1, ev.x, ev.y) != 0xFF) {
        enter(PAGE_OVERVIEW, now);
        return;
      }
      onSettings(ev, now);
    } else {
      signal_ack();  // same as ACK from the PC; no-op without an unacknowledged alarm
      if (rectContains(TOP_AREA, ev.x, ev.y)) {
        enter(PAGE_SETTINGS, now);
        return;
      }
      input_suppress(now);
    }
  }
  if (s_page == PAGE_SETTINGS && (uint32_t)(now - s_lastActivity) >= UI_IDLE_TIMEOUT_MS) {
    enter(PAGE_OVERVIEW, now);
  }
  if (s_drawStep != DRAW_DONE) {
    drawPending();
  } else if (s_page == PAGE_SETTINGS) {
    settingsRefresh(now);
  } else {
    display_overviewUpdate(now);
  }
}
