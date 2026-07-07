from state_machine import State
from sensors import SALT_CRITICAL_PCT, PRESSURE_MIN_BAR


def can_start_regeneration(sensors, current_state):
    """
    Returns (True, None) if regeneration may safely start,
    or (False, "reason") if it must be rejected.
    """
    if current_state == State.REGENERATION_RUNNING:
        return False, "Regeneration already running"
    if current_state == State.FAULT:
        return False, "Device is in FAULT state"
    if sensors.salt_level <= SALT_CRITICAL_PCT:
        return False, f"Salt level too low ({sensors.salt_level:.1f}%)"
    if sensors.water_pressure < PRESSURE_MIN_BAR:
        return False, f"Water pressure too low ({sensors.water_pressure} bar)"
    if not sensors.power_status:
        return False, "No power"
    return True, None
