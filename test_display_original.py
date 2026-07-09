# Isolation test for the ORIGINAL 1.14" Pico Display Pack (240x135, ST7789).
#
# Same Pico, same pins (SCK=18, MOSI=19, CS=17, DC=16, backlight=20) as all the
# 2.8" tests. If THIS cycles colours, the Pico + wiring + software are all good
# and the 2.8" panel is faulty. If this is ALSO blank, the problem is common to
# both (the Pico's header contacts / solder, or this Pico itself).
#
# NOTE: the 1.14" panel needs colstart/rowstart offsets, hence the extra args.

import time
import board
import busio
import displayio

try:
    from fourwire import FourWire
except ImportError:
    from displayio import FourWire
from adafruit_st7789 import ST7789

print("ORIGINAL 1.14in Pico Display Pack test")
displayio.release_displays()

spi = busio.SPI(clock=board.GP18, MOSI=board.GP19)
bus = FourWire(spi, command=board.GP16, chip_select=board.GP17)
display = ST7789(
    bus,
    rotation=270,
    width=240,
    height=135,
    rowstart=40,
    colstart=53,
    backlight_pin=board.GP20,
)
display.brightness = 1.0

group = displayio.Group()
display.root_group = group
bitmap = displayio.Bitmap(display.width, display.height, 1)
palette = displayio.Palette(1)
group.append(displayio.TileGrid(bitmap, pixel_shader=palette))

for name, color in (("RED", 0xFF0000), ("GREEN", 0x00FF00),
                    ("BLUE", 0x0000FF), ("WHITE", 0xFFFFFF)):
    palette[0] = color
    print("showing", name)
    time.sleep(1.5)

print("done - did the little screen cycle red/green/blue/white?")
