from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_event(message, level="INFO"):
    return {"time": now_iso(), "level": level, "message": message}


import os

class EventLog:
    """Keeps the most recent N events in memory and writes to a local persistent log file."""

    def __init__(self, max_entries=100, log_filename="device_activity.log"):
        self.entries = []
        self.max_entries = max_entries
        self.log_filepath = os.path.join(os.path.dirname(__file__), log_filename)
        # Clear the old log file on initialization to start fresh
        try:
            with open(self.log_filepath, "w", encoding="utf-8") as f:
                f.write(f"=== EcoWell Device Log Initialized at {now_iso()} ===\n")
        except Exception as e:
            print(f"[EventLog] Warning: Could not initialize log file: {e}")

    def add(self, message, level="INFO"):
        entry = make_event(message, level)
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)
            
        # Write to local file
        try:
            with open(self.log_filepath, "a", encoding="utf-8") as f:
                f.write(f"[{entry['time']}] [{level:5s}] {message}\n")
        except Exception as e:
            print(f"[EventLog] Warning: Could not write to log file: {e}")
            
        return entry
