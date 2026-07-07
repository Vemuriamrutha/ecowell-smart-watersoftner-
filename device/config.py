# ==============================
# DEVICE INFORMATION
# ==============================

DEVICE_ID = "ECOWELL_001"

# ==============================
# MQTT CONFIGURATION
# ==============================

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TELEMETRY_TOPIC = "ecowell/ECOWELL_001/telemetry"
MQTT_EVENT_TOPIC = "ecowell/ECOWELL_001/events"
MQTT_COMMAND_TOPIC = f"ecowell/{DEVICE_ID}/command"

# ==============================
# SENSOR LIMITS
# ==============================

MIN_FLOW = 0
MAX_FLOW = 40

MIN_PRESSURE = 0
MAX_PRESSURE = 6

MIN_SALT = 0
MAX_SALT = 100

MIN_TDS = 50
MAX_TDS = 800

# ==============================
# THRESHOLD VALUES
# ==============================

LOW_SALT_THRESHOLD = 20

LOW_PRESSURE_THRESHOLD = 1.5

HIGH_TDS_THRESHOLD = 500

# ==============================
# DEVICE TIMING
# ==============================

SENSOR_UPDATE_INTERVAL = 2

REGENERATION_DURATION = 20    # how long a successful regeneration cycle takes
REGENERATION_TIMEOUT = 60     # if not finished by then -> FAULT

# ==============================
# FILES
# ==============================

STATE_FILE = "device_state.json"
