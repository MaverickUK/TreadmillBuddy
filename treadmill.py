# =============================================================================
# Treadmill remote control via a CD4066 quad bilateral switch  (CircuitPython)
# -----------------------------------------------------------------------------
# Each GPIO pin, driven HIGH, closes one CD4066 switch which in turn "presses"
# a button on the treadmill's own remote. This is an OPEN-LOOP controller: it
# has no feedback from the treadmill, so it tracks an *assumed* current speed
# and issues the right number of +/- presses to reach a target.
# =============================================================================

import time
import board
import digitalio

import settings


def _pin(number):
    return getattr(board, "GP{}".format(number))


class TreadmillController:
    def __init__(self):
        self._up = self._output(settings.PIN_SPEED_UP)
        self._down = self._output(settings.PIN_SPEED_DOWN)
        self._start = self._output(settings.PIN_START)
        self._stop = self._output(settings.PIN_STOP)

        self.current_speed = 0.0     # our best guess at the belt speed (km/h)
        self.running = False

    # -- low level ------------------------------------------------------------
    @staticmethod
    def _output(number):
        io = digitalio.DigitalInOut(_pin(number))
        io.direction = digitalio.Direction.OUTPUT
        io.value = False             # switch open on boot (no phantom presses)
        return io

    def _press(self, pin, times=1):
        """Close/open a CD4066 switch `times` times, like tapping a button."""
        pulse = settings.BUTTON_PULSE_MS / 1000.0
        gap = settings.BUTTON_GAP_MS / 1000.0
        for _ in range(times):
            pin.value = True
            time.sleep(pulse)
            pin.value = False
            time.sleep(gap)

    # -- high level -----------------------------------------------------------
    def start(self):
        self._press(self._start)
        self.current_speed = settings.TREADMILL_START_SPEED_KPH
        self.running = True

    def stop(self):
        self._press(self._stop)
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

        self._press(self._up if delta > 0 else self._down, presses)
        self.current_speed = target
