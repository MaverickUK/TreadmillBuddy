# =============================================================================
# Treadmill Buddy - main state machine  (CircuitPython)
# -----------------------------------------------------------------------------
# CircuitPython auto-runs code.py on boot.
#
# States: SPLASH -> PLANNING -> RUNNING <-> PAUSED, RUNNING -> COMPLETED,
#         COMPLETED -> PLANNING. STOP (button X) from RUNNING/PAUSED makes a
#         fresh PLANNING screen.
#
# Buttons (2.8" Pico Display Pack):
#   A (top-left)  = Play / Pause / Resume
#   X (top-right) = Stop
# =============================================================================

import sys
import time
import board
import digitalio
import pwmio

print("=== Treadmill Buddy: code.py starting ===")

import settings
import plan as plan_lib
from treadmill import TreadmillController
from ui import UI

# --- states ---
SPLASH, PLANNING, RUNNING, PAUSED, COMPLETED = range(5)

# --- derived timings (seconds) ---
TOTAL_S = settings.SESSION_DURATION_MIN * 60
INTERVAL_S = settings.SPEED_CHANGE_INTERVAL_MIN * 60
COMPLETED_S = settings.COMPLETED_DURATION_S
DEBOUNCE_S = settings.DEBOUNCE_MS / 1000.0


def _pin(number):
    return getattr(board, "GP{}".format(number))


class Button:
    """Active-low button with debounced falling-edge detection."""

    def __init__(self, number):
        io = digitalio.DigitalInOut(_pin(number))
        io.direction = digitalio.Direction.INPUT
        io.pull = digitalio.Pull.UP
        self._io = io
        self._last = True          # True == released (pull-up)
        self._last_t = 0.0

    def pressed(self):
        value = self._io.value
        now = time.monotonic()
        hit = False
        if (not value) and self._last and (now - self._last_t) > DEBOUNCE_S:
            hit = True
            self._last_t = now
        self._last = value
        return hit


class StatusLED:
    def __init__(self):
        self._ch = None
        if settings.USE_RGB_LED:
            self._ch = (
                pwmio.PWMOut(_pin(settings.PIN_LED_R), frequency=1000, duty_cycle=0),
                pwmio.PWMOut(_pin(settings.PIN_LED_G), frequency=1000, duty_cycle=0),
                pwmio.PWMOut(_pin(settings.PIN_LED_B), frequency=1000, duty_cycle=0),
            )
            self.set(0, 0, 0)

    def set(self, r, g, b):
        if self._ch is None:
            return
        k = settings.LED_BRIGHTNESS
        for channel, value in zip(self._ch, (r, g, b)):
            duty = int(max(0, min(255, value * k)) / 255 * 65535)
            if settings.LED_COMMON_ANODE:
                duty = 65535 - duty
            channel.duty_cycle = duty


def segment_for(elapsed_s):
    seg = int(elapsed_s // INTERVAL_S)
    return seg if seg < settings.NUM_SEGMENTS else settings.NUM_SEGMENTS - 1


_ui_ref = None


def main():
    global _ui_ref
    print("- building display...")
    ui = UI()
    _ui_ref = ui
    print("- display ready")
    treadmill = TreadmillController()
    led = StatusLED()
    btn_a = Button(settings.PIN_BUTTON_A)
    btn_x = Button(settings.PIN_BUTTON_X)
    print("- I/O ready, entering state machine")

    # ----- state 1: splash -----
    led.set(255, 255, 255)
    ui.splash()
    time.sleep(settings.SPLASH_DURATION_S)

    # ----- state 2: planning -----
    plan = plan_lib.generate_plan()
    state = PLANNING

    elapsed_s = 0.0        # accumulated running time (excludes pauses)
    last_tick = 0.0        # monotonic time of the previous RUNNING update
    applied_seg = -1       # last segment whose speed we sent to the treadmill
    completed_at = 0.0

    while True:
        a = btn_a.pressed()
        x = btn_x.pressed()

        if state == PLANNING:
            led.set(0, 90, 200)
            ui.planning(plan)
            if a:                                   # start the session
                ui.starting(plan)                   # instant feedback...
                time.sleep(0.05)                    # ...let it paint before we block
                treadmill.start()                   # (this ramp blocks a few seconds)
                treadmill.set_speed(plan[0])
                applied_seg = 0
                elapsed_s = 0.0
                last_tick = time.monotonic()
                state = RUNNING
            elif x:                                 # regenerate a fresh plan
                plan = plan_lib.generate_plan()

        elif state == RUNNING:
            now = time.monotonic()
            elapsed_s += now - last_tick
            last_tick = now

            seg = segment_for(elapsed_s)
            if seg != applied_seg:                  # crossed into a new segment
                treadmill.set_speed(plan[seg])
                applied_seg = seg
                last_tick = time.monotonic()        # don't count the ramp time

            if elapsed_s >= TOTAL_S:                # -> state 5
                treadmill.stop()
                completed_at = time.monotonic()
                state = COMPLETED
            elif a:                                 # -> state 4 (pause)
                if settings.PAUSE_STOPS_BELT:
                    treadmill.stop()
                state = PAUSED
            elif x:                                 # -> new plan
                treadmill.stop()
                plan = plan_lib.generate_plan()
                applied_seg = -1
                state = PLANNING
            else:
                led.set(0, 210, 90)
                ui.session(plan, seg, elapsed_s, TOTAL_S,
                           treadmill.current_speed, paused=False)

        elif state == PAUSED:
            led.set(255, 150, 0)
            seg = segment_for(elapsed_s)
            ui.session(plan, seg, elapsed_s, TOTAL_S, plan[seg], paused=True)
            if a:                                   # resume -> state 3
                if settings.PAUSE_STOPS_BELT:
                    treadmill.start()
                    treadmill.set_speed(plan[seg])
                last_tick = time.monotonic()        # ignore time spent paused
                state = RUNNING
            elif x:                                 # -> new plan
                treadmill.stop()
                plan = plan_lib.generate_plan()
                applied_seg = -1
                state = PLANNING

        elif state == COMPLETED:
            led.set(140, 0, 220)
            left = COMPLETED_S - (time.monotonic() - completed_at)
            ui.completed(plan, elapsed_s, left)
            if left <= 0 or a or x:                 # -> state 2
                plan = plan_lib.generate_plan()
                applied_seg = -1
                state = PLANNING

        time.sleep(0.04)


try:
    main()
except Exception as exc:            # noqa: BLE001 - top-level safety net
    print("!!! Treadmill Buddy crashed:")
    sys.print_exception(exc)
    if _ui_ref is not None:
        try:
            _ui_ref.show_error("{}: {}".format(type(exc).__name__, exc))
        except Exception as exc2:
            print("(could not draw error screen)")
            sys.print_exception(exc2)
    while True:                     # hold so the message stays visible
        time.sleep(1)
