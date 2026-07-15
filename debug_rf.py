# =============================================================================
# Treadmill Buddy - RF hardware debug tool  (CircuitPython)
# -----------------------------------------------------------------------------
# Standalone check that the STX882 wiring + rf_codes.py timings actually work,
# independent of the full session state machine in code.py.
#
# Buttons (Pico Display Pack):
#   A (top-left)     -> transmit START
#   B (bottom-left)  -> transmit STOP
#   X (top-right)    -> transmit SPEED_UP
#   Y (bottom-right) -> transmit SPEED_DOWN
#
# Each press prints to the serial console and shows the action + a running
# count on the LCD, so you can watch a receiver/scope/the treadmill itself and
# confirm the input was captured and sent.
#
# To use: rename or copy this to code.py on the CIRCUITPY drive (or run it
# from the REPL), instead of the real code.py, while you test the hardware.
# =============================================================================

import time
import board
import busio
import displayio
import terminalio
import digitalio

try:
    from fourwire import FourWire            # CircuitPython 9+
except ImportError:                          # pragma: no cover
    from displayio import FourWire           # older CircuitPython

from adafruit_st7789 import ST7789
from adafruit_display_text import label

import settings
from treadmill import TreadmillController

print("=== Treadmill Buddy: RF debug tool starting ===")

WHITE = 0xFFFFFF
GREY = 0x787878
ACCENT = 0x00C8FF
GREEN = 0x00D25A


def _pin(number):
    return getattr(board, "GP{}".format(number))


class Button:
    """Active-low button with debounced falling-edge detection."""

    def __init__(self, number):
        io = digitalio.DigitalInOut(_pin(number))
        io.direction = digitalio.Direction.INPUT
        io.pull = digitalio.Pull.UP
        self._io = io
        self._last = True
        self._last_t = 0.0

    def pressed(self):
        value = self._io.value
        now = time.monotonic()
        hit = False
        debounce_s = settings.DEBOUNCE_MS / 1000.0
        if (not value) and self._last and (now - self._last_t) > debounce_s:
            hit = True
            self._last_t = now
        self._last = value
        return hit


def build_display():
    displayio.release_displays()
    spi = busio.SPI(clock=_pin(settings.PIN_LCD_SCK), MOSI=_pin(settings.PIN_LCD_MOSI))
    bus = FourWire(spi, command=_pin(settings.PIN_LCD_DC),
                   chip_select=_pin(settings.PIN_LCD_CS))
    display = ST7789(
        bus,
        width=settings.DISPLAY_WIDTH,
        height=settings.DISPLAY_HEIGHT,
        rowstart=settings.DISPLAY_ROWSTART,
        colstart=settings.DISPLAY_COLSTART,
        rotation=settings.DISPLAY_ROTATION,
        backlight_pin=_pin(settings.PIN_LCD_BL),
    )
    try:
        display.brightness = 1.0
    except Exception:
        pass
    return display


def main():
    display = build_display()
    big = display.height >= 160
    scale_title = 3 if big else 2
    scale_body = 6 if big else 3

    root = displayio.Group()
    display.root_group = root

    title = label.Label(terminalio.FONT, text="RF DEBUG", color=ACCENT, scale=scale_title)
    title.anchor_point = (0.5, 0.0)
    title.anchored_position = (display.width // 2, 6)
    root.append(title)

    action_lbl = label.Label(terminalio.FONT, text="Ready", color=WHITE, scale=scale_body)
    action_lbl.anchor_point = (0.5, 0.5)
    action_lbl.anchored_position = (display.width // 2, display.height // 2)
    root.append(action_lbl)

    count_lbl = label.Label(terminalio.FONT, text="A=Start B=Stop X=Up Y=Down",
                            color=GREY, scale=1)
    count_lbl.anchor_point = (0.5, 1.0)
    count_lbl.anchored_position = (display.width // 2, display.height - 6)
    root.append(count_lbl)

    treadmill = TreadmillController()
    btn_a = Button(settings.PIN_BUTTON_A)
    btn_b = Button(settings.PIN_BUTTON_B)
    btn_x = Button(settings.PIN_BUTTON_X)
    btn_y = Button(settings.PIN_BUTTON_Y)

    print("- I/O ready, waiting for button presses")

    presses = 0

    def fire(name, color, action):
        nonlocal presses
        presses += 1
        print("[{}] {} pressed -> transmitting".format(presses, name))
        action_lbl.text = name
        action_lbl.color = color
        action()
        print("[{}] {} sent".format(presses, name))
        count_lbl.text = "presses: {}".format(presses)

    while True:
        if btn_a.pressed():
            fire("START", GREEN, treadmill.start)
        elif btn_b.pressed():
            fire("STOP", 0xFF3030, treadmill.stop)
        elif btn_x.pressed():
            fire("UP", ACCENT, treadmill.press_speed_up)
        elif btn_y.pressed():
            fire("DOWN", 0xFFAA00, treadmill.press_speed_down)

        time.sleep(0.02)


main()
