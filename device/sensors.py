import random

# -------------------------------------------------------
# Realistic operating ranges
# -------------------------------------------------------

SENSOR_RANGES = {
    "water_flow_lpm": (0.0, 15.0),
    "water_pressure_bar": (0.0, 6.0),
    "salt_level_pct": (0.0, 100.0),
    "tds_ppm": (0, 1000),
}

# -------------------------------------------------------
# Thresholds
# -------------------------------------------------------

SALT_CRITICAL_PCT = 15
PRESSURE_MIN_BAR = 1.0
TDS_HIGH_PPM = 500


class SensorModel:
    """
    Simulates all sensors of the EcoWell water softener.
    """

    def __init__(self):

        # Initial values
        self.water_flow = 8.0
        self.water_pressure = 3.2
        self.salt_level = 80.0
        self.tds = 180.0
        self.power_status = True

        # Debug flags
        self.force_low_salt = False
        self.force_low_pressure = False
        self.force_high_tds = False
        self.force_power_failure = False

    # -------------------------------------------------------

    def update(self, is_regenerating: bool):
        """
        Updates all sensor values every simulation cycle.
        """

        # -----------------------------
        # Power
        # -----------------------------

        self.power_status = not self.force_power_failure

        if not self.power_status:
            self.water_flow = 0.0
            return

        # -----------------------------
        # Salt Level
        # -----------------------------

        if self.force_low_salt:
            self.salt_level = 10.0
        else:
            self.salt_level = max(
                0.0,
                self.salt_level - random.uniform(0.02, 0.08)
            )

        # -----------------------------
        # Water Pressure
        # -----------------------------

        if self.force_low_pressure:
            self.water_pressure = 0.5
        else:
            self.water_pressure += random.uniform(-0.05, 0.05)
            self.water_pressure = round(
                max(0.5, min(6.0, self.water_pressure)),
                2
            )

        # -----------------------------
        # TDS
        # -----------------------------

        if self.force_high_tds:
            self.tds = 650
        else:
            self.tds += random.uniform(-3, 3)
            self.tds = round(
                max(50, min(1000, self.tds)),
                1
            )

        # -----------------------------
        # Water Flow
        # -----------------------------

        if is_regenerating:
            self.water_flow = 0.0
        else:
            self.water_flow = round(
                max(
                    0.0,
                    min(
                        15.0,
                        8.0 + random.uniform(-1, 1)
                    )
                ),
                2
            )

    # -------------------------------------------------------

    def reset_debug_flags(self):

        self.force_low_salt = False
        self.force_low_pressure = False
        self.force_high_tds = False
        self.force_power_failure = False

    # -------------------------------------------------------

    def as_dict(self):

        return {
            "water_flow_lpm": self.water_flow,
            "water_pressure_bar": self.water_pressure,
            "salt_level_pct": round(self.salt_level, 1),
            "tds_ppm": self.tds,
            "power_status": self.power_status,
        }