"""
persistance.py — Save and restore device state across restarts.
Enables power-loss recovery — device resumes last known state on reboot.
"""

import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "device_state.json")


def save_state(state: str, sensors: dict):
    """Persist current state + sensor snapshot to disk."""
    try:
        payload = {"state": state, "sensors": sensors}
        with open(STATE_FILE, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"[Persist] WARNING: could not save state: {e}")


def load_state() -> dict | None:
    """Load persisted state from disk. Returns None if not found."""
    try:
        if not os.path.exists(STATE_FILE):
            return None
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Persist] WARNING: could not load state: {e}")
        return None