# =============================================================================
# Treadmill remote control via an STX882 315/433MHz OOK RF transmitter
# -----------------------------------------------------------------------------
# GP27 drives the transmitter's DATA pin directly: HIGH keys the RF carrier,
# LOW keys it off. Each button on the treadmill's own remote was captured as
# a mark/space timing list (microseconds, see rf_codes.py); replaying that
# list re-creates the same OOK envelope the remote would have sent. This is
# an OPEN-LOOP controller: it has no feedback from the treadmill, so it
# tracks an *assumed* current speed and issues the right number of +/-
# presses to reach a target.
# =============================================================================

import time
import board
import digitalio

import settings
from rf_codes import SPEED_UP, SPEED_DOWN, START, STOP


def _pin(number):
    return getattr(board, "GP{}".format(number))


def _delay_us(us):
    """Busy-wait for `us` microseconds - time.sleep()'s resolution is too
    coarse for OOK pulses a few hundred microseconds wide."""
    end = time.monotonic_ns() + us * 1000
    while time.monotonic_ns() < end:
        pass


class TreadmillController:
    def __init__(self):
        self._tx = digitalio.DigitalInOut(_pin(settings.PIN_RF_TX))
        self._tx.direction = digitalio.Direction.OUTPUT
        self._tx.value = False       # carrier off on boot

        self.current_speed = 0.0     # our best guess at the belt speed (km/h)
        self.running = False

    # -- low level ------------------------------------------------------------
    def _send(self, timings):
        """Replay one captured mark/space timing list on the TX pin."""
        level = True                 # captures always start with a mark
        for us in timings:
            self._tx.value = level
            _delay_us(us)
            level = not level
        self._tx.value = False

    def _press(self, timings, times=1):
        """Transmit a button's code `times` times, like tapping it repeatedly.

        Each "press" replays the code RF_REPEATS times back-to-back (the way
        the original remote does, so the receiver reliably decodes it), then
        waits BUTTON_GAP_MS before the next press.
        """
        gap = settings.BUTTON_GAP_MS / 1000.0
        repeat_gap = settings.RF_REPEAT_GAP_MS / 1000.0
        for _ in range(times):
            for _ in range(settings.RF_REPEATS):
                self._send(timings)
                time.sleep(repeat_gap)
            time.sleep(gap)

    # -- high level -----------------------------------------------------------
    def start(self):
        self._press(START)
        self.current_speed = settings.TREADMILL_START_SPEED_KPH
        self.running = True

    def stop(self):
        self._press(STOP)
        self.current_speed = 0.0
        self.running = False

    def set_speed(self, target):
        """Ramp the belt from the assumed current speed to `target` km/h."""
        target = round(target, 1)
        delta = round(target - self.current_speed, 1)
        step = settings.TREADMILL_SPEED_PER_PRESS_KPH
        presses = int(round(abs(delta) / step)) if step > 0 else 0

        if presses == 0:
            return

        self._press(SPEED_UP if delta > 0 else SPEED_DOWN, presses)
        self.current_speed = target
