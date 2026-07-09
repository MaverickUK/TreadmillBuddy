# =============================================================================
# Treadmill Buddy - settings  (CircuitPython)
# -----------------------------------------------------------------------------
# Everything you might want to tweak lives here. Change these values and the
# rest of the program adapts automatically (plan length, number of bars, etc).
#
# All pin values below are plain GPIO numbers, e.g. 6 means board.GP6.
# =============================================================================

# --- Software identity (shown on the splash screen) --------------------------
APP_NAME = "Treadmill Buddy"
APP_AUTHOR = "Peter Bridger"

# --- Session plan ------------------------------------------------------------
SESSION_DURATION_MIN = 45        # total length of a session, minutes
SPEED_CHANGE_INTERVAL_MIN = 5    # speed is re-evaluated every this many minutes
SPEED_STEP_KPH = 0.5             # speed goes up/down by this each interval
MIN_SPEED_KPH = 2.0              # never go below this
MAX_SPEED_KPH = 3.5              # never go above this
START_SPEED_KPH = 2.0            # speed for the first segment of the plan

# Plan generation:
#   True  -> a fresh random "walk" each session (+/- SPEED_STEP each interval,
#            clamped to MIN/MAX). Every session looks different.
#   False -> a fixed, repeatable zig-zag pattern.
RANDOM_PLAN = True

# --- Treadmill remote interface (CD4066 quad bilateral switch) ---------------
# Each GPIO drives one CD4066 switch. Driving a pin HIGH "closes" the switch,
# i.e. presses the matching button on the treadmill's own remote.
# >>> Match these to how you wired the CD4066 to the remote's button matrix. <<<
#
# These are on GP0-3, which are free on BOTH the 1.14" and the 2.0"/2.8" packs.
# (They were on GP6-9, but GP6/7/8 are the 1.14" pack's RGB LED, so idling them
# low lit the LED white. GP0-3 avoids every Display Pack peripheral.)
PIN_SPEED_UP = 0                 # remote "speed +" button   (was GP6)
PIN_SPEED_DOWN = 1               # remote "speed -" button   (was GP7)
PIN_START = 2                    # remote "start" button     (was GP8)
PIN_STOP = 3                     # remote "stop" button      (was GP9)

BUTTON_PULSE_MS = 150            # how long a switch stays closed per "press"
BUTTON_GAP_MS = 150             # pause between consecutive presses

# How much one press of the remote's speed +/- button changes the belt speed.
# Most treadmills step by 0.1 km/h per press. To achieve SPEED_STEP_KPH (0.5)
# the program will issue SPEED_STEP_KPH / this = 5 presses. Set to match yours.
TREADMILL_SPEED_PER_PRESS_KPH = 0.1

# Speed the treadmill settles at immediately after the START button is pressed.
# The program ramps up from here to the first planned speed. Set to match yours.
TREADMILL_START_SPEED_KPH = 1.0

# When paused, should the belt physically stop?
#   True  -> press STOP on pause, and on resume press START then ramp the belt
#            back up to the current segment's speed. (Recommended / safest.)
#   False -> leave the belt running; only the program's timer pauses.
PAUSE_STOPS_BELT = True

# --- Pico Display Pack LCD (ST7789) ------------------------------------------
# SPI/control pins are the same across all the Display Packs.
PIN_LCD_SCK = 18
PIN_LCD_MOSI = 19
PIN_LCD_CS = 17
PIN_LCD_DC = 16
PIN_LCD_BL = 20                  # backlight

# Which physical Display Pack you have wired up. Change this one value to
# switch panels - geometry and the on-board LED pins below derive from it
# automatically, and ui.py already adapts its whole layout to the resulting
# DISPLAY_WIDTH/HEIGHT (see UI._layout's `big` flag).
#   "2.8"  -> 320x240 Pico Display Pack 2.0" / 2.8"
#   "1.14" -> 240x135 Pico Display Pack (original)
DISPLAY_MODEL = "1.14"

_DISPLAY_PROFILES = {
    "2.8": dict(width=320, height=240, rowstart=0, colstart=0, rotation=270,
                led_r=26, led_g=27, led_b=28),
    "1.14": dict(width=240, height=135, rowstart=40, colstart=53, rotation=270,
                 led_r=6, led_g=7, led_b=8),
}
_display = _DISPLAY_PROFILES[DISPLAY_MODEL]

DISPLAY_WIDTH = _display["width"]
DISPLAY_HEIGHT = _display["height"]
DISPLAY_ROWSTART = _display["rowstart"]
DISPLAY_COLSTART = _display["colstart"]
DISPLAY_ROTATION = _display["rotation"]

# --- Pico Display Pack buttons (active-low, internal pull-up) -----------------
# Physical layout on the 2.8" pack:  A = top-left, B = bottom-left,
#                                    X = top-right, Y = bottom-right.
PIN_BUTTON_A = 12                # top-left  -> Play / Pause / Resume
PIN_BUTTON_X = 14                # top-right -> Stop
DEBOUNCE_MS = 40

# --- On-board RGB LED --------------------------------------------------------
# Status-LED feature is off for now. On the 1.14" pack the LED is on GP6/7/8;
# now that the CD4066 has moved to GP0-3, those pins are unused (high-impedance)
# so the LED stays dark on its own. Pin numbers below follow DISPLAY_MODEL
# automatically (2.8" pack: GP26/27/28, 1.14" pack: GP6/7/8).
USE_RGB_LED = False
PIN_LED_R = _display["led_r"]
PIN_LED_G = _display["led_g"]
PIN_LED_B = _display["led_b"]
LED_COMMON_ANODE = True
LED_BRIGHTNESS = 0.5             # 0.0 - 1.0 scaling applied to LED colours

# --- Screen timings ----------------------------------------------------------
SPLASH_DURATION_S = 2            # state 1
COMPLETED_DURATION_S = 30        # state 5, then back to planning

# --- Derived values (leave these alone) --------------------------------------
NUM_SEGMENTS = SESSION_DURATION_MIN // SPEED_CHANGE_INTERVAL_MIN
