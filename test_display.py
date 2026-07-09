# Display self-test v4 - BACKLIGHT PIN SWEEP.
#
# The panel is initialised and filled solid WHITE, then each candidate pin is
# driven HIGH (then, in a second pass, LOW) one at a time. WATCH THE SCREEN and
# note the GP number that is printed at the moment the screen lights up.
#
# If it lights WHITE -> that pin is the backlight and the data path works too.
# If it lights with COLOURED NOISE -> backlight found, but SPI/data has an issue.
# If nothing ever lights -> almost certainly a seating/hardware fault.

import time
import board
import busio
import digitalio
import displayio

try:
    from fourwire import FourWire
except ImportError:
    from displayio import FourWire
from adafruit_st7789 import ST7789

print("releasing displays...")
displayio.release_displays()

spi = busio.SPI(clock=board.GP18, MOSI=board.GP19)
bus = FourWire(spi, command=board.GP16, chip_select=board.GP17)
display = ST7789(bus, rotation=270, width=320, height=240)

group = displayio.Group()
display.root_group = group
bitmap = displayio.Bitmap(display.width, display.height, 1)
palette = displayio.Palette(1)
palette[0] = 0xFFFFFF
group.append(displayio.TileGrid(bitmap, pixel_shader=palette))

# candidates: skip SPI bus (16-19), CD4066 (6-9), and RGB LED (26-28)
candidates = [20, 21, 22, 0, 1, 2, 3, 10, 11, 12, 13, 14, 15, 4, 5]


def sweep(level):
    print("=== driving each pin %s ===" % ("HIGH" if level else "LOW"))
    for n in candidates:
        pin = digitalio.DigitalInOut(getattr(board, "GP%d" % n))
        pin.direction = digitalio.Direction.OUTPUT
        pin.value = level
        print("  GP%d = %s" % (n, "HIGH" if level else "LOW"))
        time.sleep(1.0)
        pin.value = not level      # relax before releasing
        pin.deinit()


sweep(True)
sweep(False)
print("done - tell me the GP number (if any) where the screen lit up")
