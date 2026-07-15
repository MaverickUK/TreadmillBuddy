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

# --- Treadmill remote interface (STX882 315/433MHz OOK RF transmitter) ------
# GP27 drives the transmitter's DATA pin directly: HIGH keys the RF carrier,
# LOW keys it off. Captured button codes (mark/space timings in microseconds)
# live in rf_codes.py - re-capture and replace those if you wire up a
# different treadmill/remote.
# NOTE: on the 2.8" Display Pack, GP27 is also the RGB LED's green channel
# (see USE_RGB_LED below) - leave USE_RGB_LED off if you use that pack, or
# move PIN_RF_TX to a free pin.
PIN_RF_TX = 27                    # STX882 DATA pin

# How many back-to-back copies of a code to send per "press", all in one
# continuous burst. The receiver fires its action once per decoded frame, not
# once per burst, so this behaves like "how long you hold the button" - too
# few and a press gets missed (decoder doesn't lock in time), too many and a
# single tap fires several times over. Tune it with debug_rf.py: hold at the
# lowest value that never misses a press.
RF_REPEATS = 6
BUTTON_GAP_MS = 150              # pause between consecutive presses

# How much one press of the remote's speed +/- button changes the belt speed.
# Most treadmills step by 0.1 km/h per press. To achieve SPEED_STEP_KPH (0.5)
# the program will issue SPEED_STEP_KPH / this = 5 presses. Set to match yours.
TREADMILL_SPEED_PER_PRESS_KPH = 0.1

# Speed the treadmill settles at immediately after the START button is pressed.
# The program ramps up from here to the first planned speed. Set to match yours.
TREADMILL_START_SPEED_KPH = 0.5

# Seconds between sending START and the belt actually moving - most treadmills
# show an on-screen countdown first. start() blocks for this long before any
# speed +/- presses are sent, so they don't get sent (and ignored) mid-countdown.
# Set to match yours.
TREADMILL_START_DELAY_S = 5

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
PIN_BUTTON_A = 12                # top-left    -> Play / Pause / Resume
PIN_BUTTON_B = 13                # bottom-left -> unused by code.py (used by debug_rf.py)
PIN_BUTTON_X = 14                # top-right   -> Stop
PIN_BUTTON_Y = 15                # bottom-right -> unused by code.py (used by debug_rf.py)
DEBOUNCE_MS = 40

# --- On-board RGB LED --------------------------------------------------------
# Status-LED feature is off for now. Pin numbers below follow DISPLAY_MODEL
# automatically (2.8" pack: GP26/27/28, 1.14" pack: GP6/7/8). The 2.8" pack's
# green channel (GP27) clashes with PIN_RF_TX above - keep this off, or move
# PIN_RF_TX, if you enable it on that pack.
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
