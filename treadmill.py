# =============================================================================
# Treadmill remote control via an STX882 315/433MHz OOK RF transmitter
# -----------------------------------------------------------------------------
# GP27 drives the transmitter's DATA pin. Each button on the treadmill's own
# remote was captured as a mark/space timing list (microseconds, EV1527-style
# - see rf_codes.py); replaying that list re-creates the same OOK envelope
# the remote would have sent.
#
# Transmission uses pulseio.PulseOut (hardware-timed via the RP2040's PIO/PWM)
# rather than a software bit-bang loop - a busy-wait loop's jitter is enough
# to make the treadmill's EV1527 decoder miss frames. duty_cycle=65535 makes
# each "on" pulse solid HIGH (no actual carrier modulation), which is what an
# ASK transmitter's DATA pin wants. Each press sends one continuous burst of
# RF_REPEATS back-to-back copies of the code, led by a sync gap so the first
# copy locks in. The receiver fires once per decoded frame, so RF_REPEATS is
# effectively "how long the button is held" - see the tuning note next to it
# in settings.py.
#
# This is an OPEN-LOOP controller: it has no feedback from the treadmill, so
# it tracks an *assumed* current speed and issues the right number of +/-
# presses to reach a target.
# =============================================================================

import time
import array
import board
import pulseio

import settings
from rf_codes import SPEED_UP, SPEED_DOWN, START, STOP, LEAD_SYNC


def _pin(number):
    return getattr(board, "GP{}".format(number))


class TreadmillController:
    def __init__(self):
        self._tx_pin = _pin(settings.PIN_RF_TX)

        self.current_speed = 0.0     # our best guess at the belt speed (km/h)
        self.running = False

    # -- low level ------------------------------------------------------------
    def _send(self, timings):
        """Burst RF_REPEATS copies of one captured code out the TX pin."""
        seq = list(LEAD_SYNC) + list(timings) * settings.RF_REPEATS
        if len(seq) % 2 == 1:
            seq.append(LEAD_SYNC[-1])    # must end on an OFF gap
        burst = array.array("H", seq)

        tx = pulseio.PulseOut(self._tx_pin, frequency=100_000, duty_cycle=65535)
        try:
            tx.send(burst)                # blocks until the whole burst is out
        finally:
            tx.deinit()

    def _press(self, timings, times=1):
        """Transmit a button's code `times` times, like tapping it repeatedly."""
        gap = settings.BUTTON_GAP_MS / 1000.0
        for _ in range(times):
            self._send(timings)
            time.sleep(gap)

    # -- high level -----------------------------------------------------------
    def start(self):
        self._press(START)
        time.sleep(settings.TREADMILL_START_DELAY_S)   # wait out the belt's own countdown
        self.current_speed = settings.TREADMILL_START_SPEED_KPH
        self.running = True

    def stop(self):
        self._press(STOP)
        self.current_speed = 0.0
        self.running = False

    def press_speed_up(self):
        """Transmit one raw SPEED_UP code, ignoring the assumed-speed tracker.

        For hardware testing (see debug_rf.py) - set_speed() below is what the
        real session logic uses.
        """
        self._press(SPEED_UP)

    def press_speed_down(self):
        """Transmit one raw SPEED_DOWN code, ignoring the assumed-speed tracker."""
        self._press(SPEED_DOWN)

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
