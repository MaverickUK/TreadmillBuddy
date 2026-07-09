# =============================================================================
# Session plan generation
# -----------------------------------------------------------------------------
# A "plan" is just a list of target speeds, one per SPEED_CHANGE_INTERVAL_MIN
# segment. len(plan) == settings.NUM_SEGMENTS.
# =============================================================================

import random
import settings


def _clamp(v):
    if v < settings.MIN_SPEED_KPH:
        return settings.MIN_SPEED_KPH
    if v > settings.MAX_SPEED_KPH:
        return settings.MAX_SPEED_KPH
    return v


def generate_plan():
    """Build the speed profile for one session.

    Starts at START_SPEED_KPH then moves +/- SPEED_STEP_KPH each segment,
    always staying within [MIN_SPEED_KPH, MAX_SPEED_KPH]. When RANDOM_PLAN is
    True the direction is random (but forced away from the limits so the plan
    always has variety); otherwise a repeatable zig-zag is produced.
    """
    speeds = [round(_clamp(settings.START_SPEED_KPH), 1)]
    step = settings.SPEED_STEP_KPH
    going_up = True

    for _ in range(settings.NUM_SEGMENTS - 1):
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


def planned_distance_km(plan):
    """Total distance the plan will cover, in km."""
    hours_per_segment = settings.SPEED_CHANGE_INTERVAL_MIN / 60.0
    return sum(plan) * hours_per_segment
