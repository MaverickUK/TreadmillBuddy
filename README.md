# Treadmill Buddy

![Pico Display showing a series of coloured bars representing the planning treadmill workout](images/treadmillbuddy.jpg "Treadmill Buddy")

Do you have a dumb treadmill that only changes speed when you manually press a
button ono the remote? Well, the Treadmill Buddy will make your dumb treadmill smart

Automated, varied-pace treadmill sessions on a Raspberry Pi Pico + Pimoroni
**Pico Display Pack**, driving a treadmill's remote by replaying its RF codes
through an **STX882** 315/433MHz OOK transmitter. Written for
**CircuitPython**. Works with either the
**2.0"/2.8" pack** (320x240) or the original **1.14" pack** (240x135) — pick
which one you have via a single setting (see [Choosing your display
pack](#choosing-your-display-pack)).

By default, a session lasts 45 minutes; every 5 minutes the target speed moves up or down
by 0.5 km/h, staying between 2.0 and 3.5 km/h. The plan is generated and shown
as a bar chart before it runs, then tracked live. This can be changed in the settings.py file.


### Video demostration
[![Watch video](https://img.youtube.com/vi/mcWXhySfC0A/mqdefault.jpg)](https://youtu.be/mcWXhySfC0A)

[Watch on YouTube](https://youtu.be/mcWXhySfC0A)

## Hardware
- Treadmill with 433MHz remote - mine is a [JTX MoveLight Walking Treadmill](https://www.jtxfitness.com/products/jtx-movelight)
- Raspberry Pi Pico
- Pimoroni [Pico Display (1.14")](https://shop.pimoroni.com/products/pico-display-pack?variant=32368664215635) or [Pico Display Pack (2.0/2.8")](https://shop.pimoroni.com/products/pico-display-pack-2-8?variant=42047194005587)
- [433MHz STX882 transmitter](https://www.ebay.co.uk/sch/i.html?_nkw=STX882)
- Optional: 433MHz SRX882 reciever - for capturing your own treadmill remote codes


## Files

| File            | Purpose                                                        |
| --------------- | -------------------------------------------------------------- |
| `settings.py`   | **All** tunable values – timings, speeds, pins, display model. Start here. |
| `plan.py`       | Generates the per-segment speed plan.                          |
| `treadmill.py`  | Open-loop STX882 RF button-presser + assumed-speed tracking.   |
| `rf_codes.py`   | Captured mark/space RF timings for each remote button.         |
| `ui.py`         | Renders the five screens with `displayio`.                     |
| `code.py`       | State machine + button handling. Auto-runs on boot.            |
| `debug_rf.py`   | Standalone hardware test: A/B/X/Y fire Start/Stop/Up/Down.     |

## Install

1. Flash the latest **CircuitPython** UF2 for the Raspberry Pi Pico from
   [circuitpython.org/board/raspberry_pi_pico](https://circuitpython.org/board/raspberry_pi_pico/).
2. From the matching [CircuitPython library bundle](https://circuitpython.org/libraries),
   copy these into the Pico's `/lib` folder:
   - `adafruit_st7789.mpy`
   - `adafruit_display_text/` (the whole folder)

   (`displayio`, `fourwire`, `vectorio`, `terminalio`, `pwmio`, `digitalio` and
   `busio` are built into CircuitPython — nothing to copy.)
3. Copy all the `.py` files in this repo to the root of the `CIRCUITPY` drive.
   `code.py` runs automatically on power-up.

## Choosing your display pack

Set `DISPLAY_MODEL` in `settings.py` to match the hardware you have:

```python
DISPLAY_MODEL = "2.8"     # 320x240 Pico Display Pack 2.0" / 2.8"
DISPLAY_MODEL = "1.14"    # 240x135 Pico Display Pack (original)
```

That one line derives the panel geometry (`DISPLAY_WIDTH/HEIGHT/ROWSTART/
COLSTART/ROTATION`) and the on-board RGB LED pins automatically — nothing
else in `settings.py` needs to change. `ui.py` picks a compact or roomy
layout at runtime based on the resulting screen height, so both sizes render
correctly with no code edits.

## The five screens

1. **Splash** – app name + author, 2 s.
2. **Planning** – bar chart of the planned trip; press **A** to start.
3. **Running** – live position on the chart, current speed, elapsed & remaining.
4. **Paused** – as running, with a "PAUSED" overlay (amber LED).
5. **Completed** – summary for 30 s, then back to a fresh plan.

## Buttons

| Button | Position   | Action                                                        |
| ------ | ---------- | ------------------------------------------------------------- |
| **A**  | top-left   | Planning→start, Running→pause, Paused→resume                  |
| **X**  | top-right  | Planning→regenerate plan, Running/Paused→stop to a new plan   |

(B and Y are unused. Any button also skips the Completed screen early.)

## Wiring

### STX882 (treadmill remote) — you must match these in `settings.py` / `rf_codes.py`
The transmitter's DATA pin is driven directly from **GP27**: HIGH keys the RF
carrier, LOW keys it off. Each button press is replayed from a captured
mark/space timing list in `rf_codes.py` — there's no per-button GPIO, since
all four "buttons" (`SPEED_UP`, `SPEED_DOWN`, `START`, `STOP`) are just
different codes sent over the same pin.

| GPIO | STX882 pin |
| ---- | ---------- |
| 27   | DATA       |

Wire the transmitter's VCC/GND to the Pico's 3.3V/5V (check your module's
rated voltage) and GND. If you have a different treadmill/remote, capture its
codes (e.g. with an RTL-SDR or a 315/433MHz receiver + logic analyzer) and
replace the timing lists in `rf_codes.py`.

GP27 is free on the 1.14" pack. On the 2.8" pack it's also the RGB LED's
green channel — see the note next to `PIN_RF_TX` in `settings.py` if you use
that pack with `USE_RGB_LED` on.

### Pico Display Pack (fixed by the hardware)
LCD (ST7789, SPI0) and button pins are identical across both packs:
SCK=GP18, MOSI=GP19, CS=GP17, DC=GP16, backlight=GP20; buttons A/B/X/Y =
GPIO 12/13/14/15 (active-low, internal pull-up). Only the panel geometry and
RGB LED pins differ, and both are set for you by `DISPLAY_MODEL` in
`settings.py`:

| Pack        | `DISPLAY_MODEL` | Resolution | RGB LED pins |
| ----------- | ---------------- | ---------- | ------------- |
| 2.0" / 2.8" | `"2.8"`          | 320x240    | GPIO 26/27/28 |
| 1.14"       | `"1.14"`         | 240x135    | GPIO 6/7/8    |

The RGB LED is common-anode and off by default (`USE_RGB_LED = False`). On
the 2.8" pack its green channel is GP27, the same pin used for the STX882
DATA line — leave `USE_RGB_LED` off on that pack (or move `PIN_RF_TX`).

## Testing the RF wiring

Before trusting the full app, copy `debug_rf.py` over `code.py` on the
`CIRCUITPY` drive (or run it from the REPL) to check the STX882 wiring and
`rf_codes.py` timings in isolation:

| Button | Action                  |
| ------ | ----------------------- |
| A      | transmit **START**      |
| B      | transmit **STOP**       |
| X      | transmit **SPEED_UP**   |
| Y      | transmit **SPEED_DOWN** |

Each press logs to the serial console and shows the action + a running press
count on the LCD, so you can confirm the button was captured while watching
a receiver/scope or the treadmill itself for the resulting signal.

## Assumptions to verify for YOUR treadmill

The controller has **no feedback** from the treadmill, so it counts button
presses against an assumed speed. Check these values in `settings.py`:

- `TREADMILL_SPEED_PER_PRESS_KPH` (default **0.1**) — how much one speed-+/−
  press changes the belt. The program issues `0.5 / this` = 5 presses per step.
- `TREADMILL_START_SPEED_KPH` (default **0.5**) — belt speed right after the
  START button; the program ramps up from here.
- `TREADMILL_START_DELAY_S` (default **5**) — how long the treadmill counts
  down after START before the belt actually moves. `start()` blocks for this
  long before sending any speed +/- presses, so they aren't sent (and
  ignored) mid-countdown.
- `PAUSE_STOPS_BELT` (default **True**) — pause presses STOP and resume presses
  START then ramps back up. Set False if your treadmill can't safely restart.
- `RF_REPEATS` (default **6**) — how many copies of a code are sent per
  press. The receiver fires once per decoded frame, so this acts like "how
  long the button is held": too low and a press gets missed, too high and
  one tap fires several times. Tune with `debug_rf.py` - find the lowest
  value that never misses a press.
- `BUTTON_GAP_MS` — pause between consecutive presses.

## Tuning the session

Everything is in `settings.py`. For example, a 30-minute session that varies
every 3 minutes between 2.5 and 4.0 km/h:

```python
SESSION_DURATION_MIN = 30
SPEED_CHANGE_INTERVAL_MIN = 3
MIN_SPEED_KPH = 2.5
MAX_SPEED_KPH = 4.0
```

The number of chart bars and plan length adjust automatically.

### Quick bench-test sessions

`SPEED_CHANGE_INTERVAL_MIN` can be a fraction of a minute, which is handy for
running a whole session end-to-end in a couple of minutes while testing the
RF wiring:

```python
SESSION_DURATION_MIN = 2          # ~2 minutes total
SPEED_CHANGE_INTERVAL_MIN = 0.25  # 15s segments -> 8 segments
```

Note the first segment already includes the fixed `TREADMILL_START_DELAY_S`
countdown (default 5s) before the belt starts ramping, so with 15s segments
its visible "at speed" time will be shorter than later segments - that's
expected, not a bug.
