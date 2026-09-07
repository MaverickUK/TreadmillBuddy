# =============================================================================
# Session plan generation
# -----------------------------------------------------------------------------
# A "plan" is just a list of target speeds, one per SPEED_CHANGE_INTERVAL_MIN
# segment. len(plan) == config.num_segments.
#
# There are two layers to it:
#   * a *base* plan - the random (or zig-zag) walk from generate_plan();
#   * a *boost* - the user's intensity setting from the planning screen, in
#     whole SPEED_STEP_KPH steps, laid on top by apply_boost() without
#     disturbing the walk underneath.
#
# SessionConfig holds what the user can change on the planning screen: the
# session length and that boost. settings.py supplies the defaults and limits.
# =============================================================================

import random
import settings


class SessionConfig:
    """The tunable parameters of the next session (see the planning screen)."""

    def __init__(self):
        self.duration_min = settings.SESSION_DURATION_MIN
        self.boost = 0                  # whole SPEED_STEP_KPH steps, +/-

    # -- derived values -------------------------------------------------------
    @property
    def num_segments(self):
        # int(...) for the same reason as settings.MAX_NUM_SEGMENTS: `//` on a
        # float interval returns a float, which range()/list use rejects.
        return int(self.duration_min // settings.SPEED_CHANGE_INTERVAL_MIN)

    @property
    def total_s(self):
        return self.duration_min * 60

    @property
    def boost_kph(self):
        """How much speed the boost adds across the whole session, in km/h."""
        return round(self.boost * settings.SPEED_STEP_KPH, 1)

    # -- adjustments (return True when something actually changed) ------------
    def adjust_time(self, steps):
        want = self.duration_min + steps * settings.TIME_STEP_MIN
        if want < settings.MIN_SESSION_DURATION_MIN:
            want = settings.MIN_SESSION_DURATION_MIN
        elif want > settings.MAX_SESSION_DURATION_MIN:
            want = settings.MAX_SESSION_DURATION_MIN
        if want == self.duration_min:
            return False
        self.duration_min = want
        return True

    def adjust_boost(self, steps, base_plan):
        """Nudge the intensity, clamped to what `base_plan` can absorb."""
        low, high = boost_limits(base_plan)
        want = self.boost + steps
        if want < low:
            want = low
        elif want > high:
            want = high
        if want == self.boost:
            return False
        self.boost = want
        return True

    def clamp_boost(self, base_plan):
        """Re-clamp after the base plan changed (e.g. a longer session)."""
        low, high = boost_limits(base_plan)
        if self.boost < low:
            self.boost = low
        elif self.boost > high:
            self.boost = high


def _clamp(v):
    if v < settings.MIN_SPEED_KPH:
        return settings.MIN_SPEED_KPH
    if v > settings.MAX_SPEED_KPH:
        return settings.MAX_SPEED_KPH
    return v


def generate_plan(cfg=None):
    """Build the base speed profile for one session.

    Starts at START_SPEED_KPH then moves +/- SPEED_STEP_KPH each segment,
    always staying within [MIN_SPEED_KPH, MAX_SPEED_KPH]. When RANDOM_PLAN is
    True the direction is random (but forced away from the limits so the plan
    always has variety); otherwise a repeatable zig-zag is produced.

    The result is the *base* plan - run it through apply_boost() to get the
    plan the user actually sees.
    """
    if cfg is None:
        cfg = SessionConfig()

    speeds = [round(_clamp(settings.START_SPEED_KPH), 1)]
    step = settings.SPEED_STEP_KPH
    going_up = True

    for _ in range(cfg.num_segments - 1):
        prev = speeds[-1]

        if prev <= settings.MIN_SPEED_KPH:
            direction = +1          # at the floor -> must go up
        elif prev >= settings.MAX_SPEED_KPH:
            direction = -1          # at the ceiling -> must go down
        elif settings.RANDOM_PLAN:
            direction = random.choice((-1, 1))
        else:
            direction = 1 if going_up else -1
            going_up = not going_up

        speeds.append(round(_clamp(prev + direction * step), 1))

    return speeds


def boost_limits(base_plan):
    """(min, max) boost steps `base_plan` can take before it hits the limits.

    The maximum is "every segment at MAX_SPEED_KPH", the minimum "every segment
    at MIN_SPEED_KPH" - so the boost can never push a segment out of range.
    """
    step = settings.SPEED_STEP_KPH
    if step <= 0 or not base_plan:
        return 0, 0
    up = sum(int(round((settings.MAX_SPEED_KPH - s) / step)) for s in base_plan)
    down = sum(int(round((s - settings.MIN_SPEED_KPH) / step)) for s in base_plan)
    return -down, up


def apply_boost(base_plan, steps):
    """Lay `steps` x SPEED_STEP_KPH on top of `base_plan`, one segment a press.

    Going up, each step lifts the slowest segment (earliest one on a tie), so
    the valleys fill in first and the total climbs by exactly SPEED_STEP_KPH
    per press. Going down, each step drops the fastest segment. Segments that
    have reached MAX/MIN_SPEED_KPH are skipped, so nothing leaves the band.

    A segment is also skipped if bumping it would make it equal to either
    neighbour - every segment boundary must be a real speed change, so the
    treadmill isn't sent a no-op speed at the point it's supposed to move -
    unless every remaining candidate would tie a neighbour, in which case one
    is allowed through rather than dropping the press entirely. Any tie that
    slips through anyway (e.g. boost extremes pin several segments to the same
    limit) is cleaned up afterwards by _dedupe_adjacent().
    """
    plan = list(base_plan)
    step = settings.SPEED_STEP_KPH
    up = steps > 0

    for _ in range(abs(steps)):
        pick = _pick_boost_segment(plan, up, step, avoid_ties=True)
        if pick < 0:
            pick = _pick_boost_segment(plan, up, step, avoid_ties=False)
        if pick < 0:                    # fully boosted / fully backed off
            break
        plan[pick] = round(plan[pick] + (step if up else -step), 1)

    return _dedupe_adjacent(plan)


def _pick_boost_segment(plan, up, step, avoid_ties):
    """Pick the segment apply_boost() should nudge next, or -1 if none qualify."""
    pick = -1
    for i, s in enumerate(plan):
        if up:
            if s >= settings.MAX_SPEED_KPH:
                continue
        else:
            if s <= settings.MIN_SPEED_KPH:
                continue

        if avoid_ties:
            new_val = round(s + (step if up else -step), 1)
            if i > 0 and plan[i - 1] == new_val:
                continue
            if i < len(plan) - 1 and plan[i + 1] == new_val:
                continue

        if pick < 0 or (up and s < plan[pick]) or (not up and s > plan[pick]):
            pick = i
    return pick


def _dedupe_adjacent(plan):
    """Nudge any segment left tied to its predecessor so every boundary in the
    final plan is a real speed change, however it was produced.

    Walking left to right, each fix only has to differ from the segment
    before it (already resolved by the previous iteration), so this always
    succeeds as long as the speed band has at least two grid points -
    otherwise (e.g. MIN/MAX_SPEED_KPH too close together) the tie is left in
    place rather than pushing a speed out of range.
    """
    lo, hi = settings.MIN_SPEED_KPH, settings.MAX_SPEED_KPH
    step = settings.SPEED_STEP_KPH
    if step <= 0:
        return plan

    for i in range(1, len(plan)):
        if plan[i] != plan[i - 1]:
            continue
        options = []
        for delta in (step, -step):
            cand = round(plan[i] + delta, 1)
            if lo <= cand <= hi and cand != plan[i - 1]:
                options.append(cand)
        if not options:
            continue                    # no room to break the tie - leave it
        next_val = plan[i + 1] if i + 1 < len(plan) else None
        plan[i] = next((o for o in options if o != next_val), options[0])

    return plan


def planned_distance_km(plan):
    """Total distance the plan will cover, in km."""
    hours_per_segment = settings.SPEED_CHANGE_INTERVAL_MIN / 60.0
    return sum(plan) * hours_per_segment
