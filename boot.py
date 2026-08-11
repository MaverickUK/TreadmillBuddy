# =============================================================================
# Treadmill Buddy - boot-time setup  (CircuitPython)
# -----------------------------------------------------------------------------
# CircuitPython runs boot.py once, before code.py. All we do here is hold the
# LCD backlight off: from power-up until ui.py initialises the ST7789 its frame
# RAM holds garbage, which otherwise shows as a second or two of noise and
# scrambled visuals before the splash screen appears.
#
# CircuitPython resets every pin between boot.py and code.py, so this only
# covers the boot phase - ui.py re-asserts the backlight low the moment it
# starts, and only switches it on once the first (black) frame is on the panel.
# =============================================================================

import board
import digitalio

import settings

try:
    _bl = digitalio.DigitalInOut(getattr(board, "GP{}".format(settings.PIN_LCD_BL)))
    _bl.switch_to_output(value=False)
except Exception as exc:            # never let boot.py stop code.py running
    print("boot.py: could not hold backlight off:", exc)
