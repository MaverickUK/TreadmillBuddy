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

import time

import board
import busio
import digitalio
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

# terminalio's built-in font is a fixed 6x8 pixel cell - text sizing below
# multiplies these by the label's scale.
GLYPH_W = 6
GLYPH_H = 8

# planning-screen edit modes (which field X/Y adjust; B swaps between them)
EDIT_TIME, EDIT_INTENSITY = range(2)


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
    lo, hi = settings.MIN_SPEED_KPH, settings.MAX_SPEED_KPH
    span = hi - lo
    t = 0.0 if span <= 0 else _clamp01((speed - lo) / span)
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

        # Backlight first, and OFF: from power-up until the ST7789 is
        # initialised its frame RAM holds garbage, which shows as a second or
        # two of noise. We drive the backlight ourselves (rather than handing
        # the pin to ST7789, which switches it on immediately) and only turn it
        # on once a black, fully-built first frame has been pushed out.
        self._backlight = digitalio.DigitalInOut(_pin(settings.PIN_LCD_BL))
        self._backlight.switch_to_output(value=False)

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
        )
        self.display.auto_refresh = False

        self.W = self.display.width
        self.H = self.display.height
        self._layout()

        self.cfg = plan_lib.SessionConfig()   # replaced by planning()/session()
        self._active_bars = 0

        self.root = displayio.Group()
        self.display.root_group = self.root
        self.root.append(self._rect(self.W, self.H, 0, 0, BLACK))  # background

        self._build_splash()
        self._build_content()
        self._build_completed()
        self._build_alert()

        self.g_splash.hidden = True
        self.g_content.hidden = True
        self.g_completed.hidden = True
        self.g_alert.hidden = True

        self._first_frame()

    def _first_frame(self):
        """Push the (all-black) scene out, then light the panel up."""
        for _ in range(10):
            if self.display.refresh(minimum_frames_per_second=0):
                break
            time.sleep(0.02)
        self.display.auto_refresh = True
        time.sleep(0.05)
        self._backlight.value = True

    # -- refresh control --------------------------------------------------
    def pause_refresh(self):
        """Stop background auto-refresh so nothing competes for the CPU/SPI
        bus during time-critical work (e.g. an RF burst)."""
        self.display.auto_refresh = False

    def resume_refresh(self):
        """Push out anything drawn while paused, then resume auto-refresh."""
        self.display.refresh()
        self.display.auto_refresh = True

    # -- layout profile (depends on panel size) -------------------------------
    def _layout(self):
        big = self.H >= 160
        self.big = big

        self.chart_left = 12 if big else 6
        self.chart_top = 90 if big else 48
        self.chart_bottom = self.H - (16 if big else 12)

        # text scales
        self.s_splash = 5 if big else 2
        self.s_author = 2 if big else 1
        self.s_title = 3 if big else 2
        self.s_sub = 2 if big else 1
        self.s_mode = 2 if big else 1
        self.s_hint = 1
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

        # "TREADMILL BUDDY" at splash scale is far wider than either panel, so
        # break it onto one line per word and shrink the scale until the
        # longest word fits.
        words = settings.APP_NAME.split() or [settings.APP_NAME]
        longest = max(len(w) for w in words)
        scale = self.s_splash
        while scale > 1 and longest * GLYPH_W * scale > self.W - 16:
            scale -= 1

        line_h = GLYPH_H * scale + (10 if self.big else 4)
        centre_y = int(self.H * 0.38)
        top_y = centre_y - (len(words) - 1) * line_h // 2
        for i, word in enumerate(words):
            self.g_splash.append(self._label(word, scale, ACCENT, self.W // 2,
                                             top_y + i * line_h, (0.5, 0.5)))

        auth_y = 175 if self.big else 90
        self.g_splash.append(self._label("by " + settings.APP_AUTHOR, self.s_author,
                                         GREY, self.W // 2, auth_y, (0.5, 0.5)))
        ver_y = auth_y + (16 if self.big else 10)
        self.g_splash.append(self._label("v" + settings.APP_VERSION, self.s_hint,
                                         GREY, self.W // 2, ver_y, (0.5, 0.5)))
        self.root.append(self.g_splash)

    def _build_content(self):
        self.g_content = displayio.Group()
        n = settings.MAX_NUM_SEGMENTS      # worst case; extras get hidden

        # bars + value labels
        self.bars = []
        self.bar_labels = []
        for _ in range(n):
            r = self._rect(1, 14, 0, 0, GREEN)
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

        # planning-only text: title, the two adjustable fields (the one B has
        # selected is highlighted), and a hint line.
        self.g_planning = displayio.Group()
        if self.big:
            title_y, mode_y, hint_y = 20, 52, 78
        else:
            title_y, mode_y, hint_y = 10, 27, 39
        self.title = self._label("SESSION PLAN", self.s_title, WHITE,
                                 self.W // 2, title_y, (0.5, 0.5))
        self.time_lbl = self._label("", self.s_mode, ACCENT,
                                    self.chart_left, mode_y, (0.0, 0.5))
        self.intensity_lbl = self._label("", self.s_mode, GREY,
                                         self.W - self.chart_left, mode_y, (1.0, 0.5))
        self.hint = self._label("", self.s_hint, GREY, self.W // 2, hint_y, (0.5, 0.5))
        for lbl in (self.title, self.time_lbl, self.intensity_lbl, self.hint):
            self.g_planning.append(lbl)
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

    def _build_alert(self):
        """Full-screen speed-change screen: one big triangle on black.

        Both triangles are built up front and share a palette, so showing one
        is just a hidden flag plus a colour write.
        """
        self.g_alert = displayio.Group()
        self.g_alert.append(self._rect(self.W, self.H, 0, 0, BLACK))

        margin = 10
        th = self.H - 2 * margin
        tw = min(self.W - 2 * margin, int(self.H * 1.05))
        x = (self.W - tw) // 2
        y = margin

        self._alert_pal = displayio.Palette(1)
        self._alert_pal[0] = GREEN
        self.tri_up = vectorio.Polygon(
            pixel_shader=self._alert_pal,
            points=[(0, th), (tw, th), (tw // 2, 0)], x=x, y=y)
        self.tri_down = vectorio.Polygon(
            pixel_shader=self._alert_pal,
            points=[(0, 0), (tw, 0), (tw // 2, th)], x=x, y=y)
        self.g_alert.append(self.tri_up)
        self.g_alert.append(self.tri_down)
        self.root.append(self.g_alert)

    # -- bar geometry (recomputed only when the plan changes) -----------------
    def _apply_plan(self, plan, cfg):
        lo = settings.MIN_SPEED_KPH
        span = settings.MAX_SPEED_KPH - lo
        usable = self.chart_bottom - self.chart_top
        min_bar = 14 if self.big else 10
        area = self.W - 2 * self.chart_left
        slot = area / len(plan)

        # Bars butt up against each other: each one runs from its slot's left
        # edge to the next one's, so rounding never leaves a gap.
        for i, s in enumerate(plan):
            frac = 0.0 if span <= 0 else _clamp01((s - lo) / span)
            h = int(min_bar + frac * (usable - min_bar))
            x = int(self.chart_left + i * slot)
            w = max(1, int(self.chart_left + (i + 1) * slot) - x)
            y = self.chart_bottom - h

            r = self.bars[i]
            r.hidden = False
            r.width = w
            r.height = h
            r.x = x
            r.y = y
            r.pixel_shader[0] = _speed_color(s)

            lb = self.bar_labels[i]
            # "0.0" needs 3 glyphs; drop the labels rather than let them
            # overlap once the bars get narrow (long sessions).
            lb.hidden = w < 3 * GLYPH_W * self.s_bar
            lb.text = "%.1f" % s
            lb.anchored_position = (int(x + w / 2), y - 2)

        for i in range(len(plan), len(self.bars)):
            self.bars[i].hidden = True
            self.bar_labels[i].hidden = True
            self.bar_overlays[i].hidden = True

        self._active_bars = len(plan)
        self.cfg = cfg

    # -- public screen API ----------------------------------------------------
    def splash(self):
        self.g_splash.hidden = False
        self.g_content.hidden = True
        self.g_completed.hidden = True
        self.g_alert.hidden = True

    def planning(self, plan, cfg, edit_mode=EDIT_TIME):
        self._apply_plan(plan, cfg)

        # the boost reads as a running total: every X press is +0.5 km/h across
        # the session, every Y press takes 0.5 back off again
        kph = cfg.boost_kph
        sign = "+" if kph > 0 else ("-" if kph < 0 else "")
        self.time_lbl.text = "TIME %dm" % cfg.duration_min
        self.intensity_lbl.text = "SPEED %s%.1f" % (sign, abs(kph))
        editing_time = edit_mode == EDIT_TIME
        self.time_lbl.color = ACCENT if editing_time else GREY
        self.intensity_lbl.color = GREY if editing_time else ACCENT
        self.hint.text = "%.2f km   X + / Y -   B swap   A start" % (
            plan_lib.planned_distance_km(plan),)

        self.g_splash.hidden = True
        self.g_completed.hidden = True
        self.g_alert.hidden = True
        self.g_content.hidden = False
        self.g_planning.hidden = False
        self.g_running.hidden = True
        self.g_paused.hidden = True
        self.g_starting.hidden = True

    def starting(self, plan, cfg, edit_mode=EDIT_TIME):
        """Planning chart with a big STARTING overlay (immediate A feedback)."""
        self.planning(plan, cfg, edit_mode)
        self.g_starting.hidden = False

    def speed_change(self, speed, direction):
        """Blank the screen and show one big triangle for a speed change.

        `direction` is +1 (speeding up) or -1 (slowing down); the triangle is
        drawn in the colour of `speed`, i.e. the stage about to start.

        Auto-refresh is paused across all of this and the frame is pushed out
        once at the end - otherwise the colour swap, the triangle-visibility
        flip and the group-hidden changes below can each get pushed to the
        panel as separate partial frames, which shows up as a visible glitch
        (e.g. the old triangle briefly in the new colour, or a flash of the
        content screen) during the transition.
        """
        self.pause_refresh()
        self._alert_pal[0] = _speed_color(speed)
        self.tri_up.hidden = direction < 0
        self.tri_down.hidden = direction > 0

        self.g_splash.hidden = True
        self.g_content.hidden = True
        self.g_completed.hidden = True
        self.g_alert.hidden = False
        self.resume_refresh()

    def session(self, plan, cfg, seg, elapsed_s, total_s, speed, paused):
        if self._active_bars != len(plan) or self.cfg is not cfg:
            self._apply_plan(plan, cfg)

        self.g_splash.hidden = True
        self.g_completed.hidden = True
        self.g_alert.hidden = True
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
        for i in range(self._active_bars):
            bar = self.bars[i]
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
        self.g_alert.hidden = True
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
        self.g_alert.hidden = True
        self.g_error.hidden = False
