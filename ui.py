# =============================================================================
# Screen rendering for Pimoroni Pico Display Packs (ST7789)  -- CircuitPython
# -----------------------------------------------------------------------------
# Panel geometry comes from settings, so the same code runs on the 1.14"
# (240x135) and the 2.0"/2.8" (320x240) packs. Layout uses a compact profile on
# short panels and a roomier one on tall panels.
#
# displayio keeps a retained scene graph: we build every element once, then just
# update text / positions / colours and toggle group visibility.
# =============================================================================

import board
import busio
import displayio
import vectorio
import terminalio

try:
    from fourwire import FourWire            # CircuitPython 9+
except ImportError:                          # pragma: no cover
    from displayio import FourWire           # older CircuitPython

from adafruit_st7789 import ST7789
from adafruit_display_text import label

import settings
import plan as plan_lib

# --- colours (0xRRGGBB) ---
BLACK = 0x000000
WHITE = 0xFFFFFF
GREY = 0x787878
GREEN = 0x00D25A
AMBER = 0xFFAA00
ACCENT = 0x00C8FF


def _pin(number):
    return getattr(board, "GP{}".format(number))


def _fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    return "%02d:%02d" % (seconds // 60, seconds % 60)


def _lerp(a, b, t):
    return int(a + (b - a) * t)


def _clamp01(t):
    if t < 0:
        return 0.0
    if t > 1:
        return 1.0
    return t


def _speed_color(speed):
    """Slow -> fast as green -> yellow -> orange -> red, as 0xRRGGBB.

    Routing through yellow keeps the middle speeds vivid and distinct instead of
    the muddy brown a straight green->red blend would give.
    """
    span = settings.MAX_SPEED_KPH - settings.MIN_SPEED_KPH
    t = 0.0 if span <= 0 else _clamp01((speed - settings.MIN_SPEED_KPH) / span)
    if t < 0.5:                          # green -> yellow
        u = t / 0.5
        r, g, b = _lerp(0, 240, u), _lerp(200, 210, u), _lerp(60, 0, u)
    else:                                # yellow -> red
        u = (t - 0.5) / 0.5
        r, g, b = _lerp(240, 230, u), _lerp(210, 40, u), _lerp(0, 40, u)
    return (r << 16) | (g << 8) | b


PAST_GRAY = 0x555555


class UI:
    def __init__(self):
        displayio.release_displays()
        spi = busio.SPI(clock=_pin(settings.PIN_LCD_SCK), MOSI=_pin(settings.PIN_LCD_MOSI))
        bus = FourWire(spi, command=_pin(settings.PIN_LCD_DC),
                       chip_select=_pin(settings.PIN_LCD_CS))
        self.display = ST7789(
            bus,
            width=settings.DISPLAY_WIDTH,
            height=settings.DISPLAY_HEIGHT,
            rowstart=settings.DISPLAY_ROWSTART,
            colstart=settings.DISPLAY_COLSTART,
            rotation=settings.DISPLAY_ROTATION,
            backlight_pin=_pin(settings.PIN_LCD_BL),
        )
        try:
            self.display.brightness = 1.0
        except Exception:
            pass

        self.W = self.display.width
        self.H = self.display.height
        self._layout()

        self.root = displayio.Group()
        self.display.root_group = self.root
        self.root.append(self._rect(self.W, self.H, 0, 0, BLACK))  # background

        self._build_splash()
        self._build_content()
        self._build_completed()

        self.g_splash.hidden = True
        self.g_content.hidden = True
        self.g_completed.hidden = True

    # -- layout profile (depends on panel size) -------------------------------
    def _layout(self):
        big = self.H >= 160
        self.big = big

        self.chart_left = 12 if big else 6
        self.chart_top = 88 if big else 44
        self.chart_bottom = self.H - (16 if big else 12)

        area = self.W - 2 * self.chart_left
        self.barw = int((area / settings.NUM_SEGMENTS) * 0.72)

        # text scales
        self.s_splash = 5 if big else 2
        self.s_author = 2 if big else 1
        self.s_title = 3 if big else 2
        self.s_sub = 2 if big else 1
        self.s_speed = 6 if big else 3
        self.s_kmh = 2 if big else 1
        self.s_ttl = 1
        self.s_tval = 2 if big else 1
        self.s_done = 5 if big else 2
        self.s_stats = 2 if big else 1
        self.s_paused = 4 if big else 2
        self.s_bar = 1

    # -- element helpers ------------------------------------------------------
    def _rect(self, w, h, x, y, color):
        pal = displayio.Palette(1)
        pal[0] = color
        return vectorio.Rectangle(pixel_shader=pal, width=max(1, int(w)),
                                  height=max(1, int(h)), x=int(x), y=int(y))

    def _label(self, text, scale, color, x, y, anchor):
        lbl = label.Label(terminalio.FONT, text=text, color=color, scale=scale)
        lbl.anchor_point = anchor
        lbl.anchored_position = (int(x), int(y))
        return lbl

    # -- screen construction --------------------------------------------------
    def _build_splash(self):
        self.g_splash = displayio.Group()
        name_y = 90 if self.big else 45
        auth_y = 165 if self.big else 82
        self.g_splash.append(self._label(settings.APP_NAME, self.s_splash, ACCENT,
                                         self.W // 2, name_y, (0.5, 0.5)))
        self.g_splash.append(self._label("by " + settings.APP_AUTHOR, self.s_author,
                                         GREY, self.W // 2, auth_y, (0.5, 0.5)))
        self.root.append(self.g_splash)

    def _build_content(self):
        self.g_content = displayio.Group()
        n = settings.NUM_SEGMENTS

        # bars + value labels
        self.bars = []
        self.bar_labels = []
        for _ in range(n):
            r = self._rect(self.barw, 14, 0, 0, GREEN)
            self.g_content.append(r)
            self.bars.append(r)
        for _ in range(n):
            lb = self._label("0.0", self.s_bar, GREY, 0, 0, (0.5, 1.0))
            self.g_content.append(lb)
            self.bar_labels.append(lb)

        # baseline
        self.g_content.append(self._rect(self.W - 2 * self.chart_left, 2,
                                         self.chart_left, self.chart_bottom, GREY))

        # running-only overlay (drawn ON TOP of the bars)
        self.g_running = displayio.Group()

        # one grey rectangle per bar: covers the "already passed" portion of the
        # bar (full bar once behind the tracker, or a left slice while under it).
        self._gray_pal = displayio.Palette(1)
        self._gray_pal[0] = PAST_GRAY
        self.bar_overlays = []
        for _ in range(n):
            ov = vectorio.Rectangle(pixel_shader=self._gray_pal,
                                    width=1, height=1, x=-10, y=0)
            ov.hidden = True
            self.g_running.append(ov)
            self.bar_overlays.append(ov)

        # progress tracker line, drawn on top of the grey
        self.progress = self._rect(2, (self.chart_bottom - self.chart_top) + 4,
                                   self.chart_left, self.chart_top - 4, ACCENT)
        self.g_running.append(self.progress)

        # big current speed stays top-left; elapsed + remaining sit side by side
        # to the RIGHT of it.
        if self.big:
            self.speed_lbl = self._label("0.0", self.s_speed, GREEN, 12, 8, (0.0, 0.0))
            self.kmh_lbl = self._label("km/h", self.s_kmh, GREY, 150, 78, (0.0, 1.0))
            el_x, rm_x, ty_title, ty_val = 140, 230, 10, 26
        else:
            self.speed_lbl = self._label("0.0", self.s_speed, GREEN, 6, 4, (0.0, 0.0))
            self.kmh_lbl = self._label("km/h", self.s_kmh, GREY, 64, 28, (0.0, 1.0))
            el_x, rm_x, ty_title, ty_val = 90, 160, 4, 14

        self.el_title = self._label("ELAPSED", self.s_ttl, GREY, el_x, ty_title, (0.0, 0.0))
        self.el_val = self._label("00:00", self.s_tval, WHITE, el_x, ty_val, (0.0, 0.0))
        self.rm_title = self._label("REMAINING", self.s_ttl, GREY, rm_x, ty_title, (0.0, 0.0))
        self.rm_val = self._label("00:00", self.s_tval, WHITE, rm_x, ty_val, (0.0, 0.0))
        for lbl in (self.speed_lbl, self.kmh_lbl, self.el_title, self.el_val,
                    self.rm_title, self.rm_val):
            self.g_running.append(lbl)
        self.g_content.append(self.g_running)

        # planning-only text
        self.g_planning = displayio.Group()
        title_y = 22 if self.big else 12
        sub_y = 52 if self.big else 30
        self.title = self._label("SESSION PLAN", self.s_title, WHITE,
                                 self.W // 2, title_y, (0.5, 0.5))
        self.subtitle = self._label("", self.s_sub, GREY, self.W // 2, sub_y, (0.5, 0.5))
        self.g_planning.append(self.title)
        self.g_planning.append(self.subtitle)
        self.g_content.append(self.g_planning)

        # paused overlay (front-most)
        self.g_paused = displayio.Group()
        bw, bh = (200, 66) if self.big else (150, 40)
        self.g_paused.append(self._rect(bw + 6, bh + 6, (self.W - bw - 6) // 2,
                                        (self.H - bh - 6) // 2, BLACK))
        self.g_paused.append(self._rect(bw, bh, (self.W - bw) // 2,
                                        (self.H - bh) // 2, AMBER))
        self.g_paused.append(self._label("PAUSED", self.s_paused, BLACK,
                                         self.W // 2, self.H // 2, (0.5, 0.5)))
        self.g_content.append(self.g_paused)

        # "STARTING" overlay - shown the instant A is pressed, before the belt
        # ramp (which blocks for a couple of seconds) begins.
        self.g_starting = displayio.Group()
        sbw, sbh = (240, 66) if self.big else (190, 40)
        self.g_starting.append(self._rect(sbw + 6, sbh + 6, (self.W - sbw - 6) // 2,
                                          (self.H - sbh - 6) // 2, BLACK))
        self.g_starting.append(self._rect(sbw, sbh, (self.W - sbw) // 2,
                                          (self.H - sbh) // 2, GREEN))
        self.g_starting.append(self._label("STARTING", self.s_paused, BLACK,
                                           self.W // 2, self.H // 2, (0.5, 0.5)))
        self.g_content.append(self.g_starting)

        self.root.append(self.g_content)

    def _build_completed(self):
        self.g_completed = displayio.Group()
        if self.big:
            ys = (55, 105, 155, 195)
        else:
            ys = (28, 52, 82, 104)
        self.g_completed.append(self._label("SESSION", self.s_done, GREEN,
                                            self.W // 2, ys[0], (0.5, 0.5)))
        self.g_completed.append(self._label("COMPLETE", self.s_done, GREEN,
                                            self.W // 2, ys[1], (0.5, 0.5)))
        self.cmp_stats = self._label("", self.s_stats, WHITE, self.W // 2, ys[2], (0.5, 0.5))
        self.cmp_count = self._label("", self.s_stats, GREY, self.W // 2, ys[3], (0.5, 0.5))
        self.g_completed.append(self.cmp_stats)
        self.g_completed.append(self.cmp_count)
        self.root.append(self.g_completed)

    # -- bar geometry (recomputed only when the plan changes) -----------------
    def _apply_plan(self, plan):
        span = settings.MAX_SPEED_KPH - settings.MIN_SPEED_KPH
        usable = self.chart_bottom - self.chart_top
        min_bar = 14 if self.big else 10
        slot = (self.W - 2 * self.chart_left) / len(plan)

        for i, s in enumerate(plan):
            frac = 0.0 if span <= 0 else _clamp01((s - settings.MIN_SPEED_KPH) / span)
            h = int(min_bar + frac * (usable - min_bar))
            x = int(self.chart_left + i * slot + (slot - self.barw) / 2)
            y = self.chart_bottom - h

            r = self.bars[i]
            r.width = self.barw
            r.height = h
            r.x = x
            r.y = y
            r.pixel_shader[0] = _speed_color(s)

            lb = self.bar_labels[i]
            lb.text = "%.1f" % s
            lb.anchored_position = (int(x + self.barw / 2), y - 2)

    # -- public screen API ----------------------------------------------------
    def splash(self):
        self.g_splash.hidden = False
        self.g_content.hidden = True
        self.g_completed.hidden = True

    def planning(self, plan):
        self._apply_plan(plan)
        if self.big:
            self.subtitle.text = "%d min  %.2f km  -  press A" % (
                settings.SESSION_DURATION_MIN, plan_lib.planned_distance_km(plan))
        else:
            self.subtitle.text = "%dmin %.1fkm - press A" % (
                settings.SESSION_DURATION_MIN, plan_lib.planned_distance_km(plan))

        self.g_splash.hidden = True
        self.g_completed.hidden = True
        self.g_content.hidden = False
        self.g_planning.hidden = False
        self.g_running.hidden = True
        self.g_paused.hidden = True
        self.g_starting.hidden = True

    def starting(self, plan):
        """Planning chart with a big STARTING overlay (immediate A feedback)."""
        self.planning(plan)
        self.g_starting.hidden = False

    def session(self, plan, seg, elapsed_s, total_s, speed, paused):
        self.g_splash.hidden = True
        self.g_completed.hidden = True
        self.g_content.hidden = False
        self.g_planning.hidden = True
        self.g_running.hidden = False
        self.g_starting.hidden = True

        self.speed_lbl.text = "%.1f" % speed
        self.speed_lbl.color = AMBER if paused else GREEN
        self.el_val.text = _fmt_time(elapsed_s)
        self.rm_val.text = _fmt_time(total_s - elapsed_s)

        area = self.W - 2 * self.chart_left
        frac = _clamp01(elapsed_s / total_s) if total_s else 0.0
        progress_x = int(self.chart_left + frac * area)
        self.progress.x = progress_x

        # grey out the passed part of each bar; split the bar under the tracker
        for i, bar in enumerate(self.bars):
            overlay = self.bar_overlays[i]
            left = bar.x
            right = bar.x + bar.width
            if progress_x >= right:                 # bar fully passed -> all grey
                overlay.x = bar.x
                overlay.y = bar.y
                overlay.width = bar.width
                overlay.height = bar.height
                overlay.hidden = False
            elif progress_x <= left:                # bar still ahead -> no grey
                overlay.hidden = True
            else:                                   # tracker over this bar -> split
                overlay.x = bar.x
                overlay.y = bar.y
                overlay.width = max(1, progress_x - left)
                overlay.height = bar.height
                overlay.hidden = False

        self.g_paused.hidden = not paused

    def completed(self, plan, elapsed_s, seconds_left):
        self.cmp_stats.text = "%s  %.2f km" % (
            _fmt_time(elapsed_s), plan_lib.planned_distance_km(plan))
        self.cmp_count.text = "new plan in %ds" % int(seconds_left)

        self.g_splash.hidden = True
        self.g_content.hidden = True
        self.g_completed.hidden = False

    def show_error(self, message):
        """Fatal-error screen: red banner + wrapped message text."""
        if not hasattr(self, "g_error"):
            self.g_error = displayio.Group()
            self.g_error.append(self._label("ERROR", self.s_title, 0xFF3030,
                                            self.W // 2, 14 if not self.big else 24,
                                            (0.5, 0.5)))
            self._err_body = label.Label(terminalio.FONT, text="", color=WHITE,
                                         scale=1, line_spacing=1.1)
            self._err_body.anchor_point = (0.0, 0.0)
            self._err_body.anchored_position = (4, 30 if not self.big else 52)
            self.g_error.append(self._err_body)
            self.root.append(self.g_error)

        wrap = max(10, (self.W // 6) - 1)
        text = str(message)
        lines = []
        while text:
            lines.append(text[:wrap])
            text = text[wrap:]
        self._err_body.text = "\n".join(lines[:10])

        self.g_splash.hidden = True
        self.g_content.hidden = True
        self.g_completed.hidden = True
        self.g_error.hidden = False
