"""Constants for the 2N Intercom integration."""

DOMAIN = "two_n_intercom"

# Configuration keys
CONF_POLL_INTERVAL = "poll_interval"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"

# Default values
DEFAULT_POLL_INTERVAL = 30  # seconds
DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_USE_SSL = True
DEFAULT_VERIFY_SSL = False

# Snapshot defaults
DEFAULT_SNAPSHOT_WIDTH = 640
DEFAULT_SNAPSHOT_HEIGHT = 480
DEFAULT_SNAPSHOT_SOURCE = "internal"

# API endpoints (based on Homebridge plugin behavior)
API_STATUS = "/api/system/status"
API_SWITCH_CAPS = "/api/switch/caps"
API_SWITCH_CTRL = "/api/switch/ctrl"
API_CALL_STATUS = "/api/call/status"
API_CAMERA_SNAPSHOT = "/api/camera/snapshot"

# Entity unique ID prefixes
CAMERA_PREFIX = "camera"
SWITCH_PREFIX = "switch"
BINARY_SENSOR_PREFIX = "binary_sensor"
EVENT_PREFIX = "event"

# Switch types
SWITCH_CAMERA = "camera"
SWITCH_MICROPHONE = "microphone"
SWITCH_AUTO_OPEN = "auto_open"

# Binary sensor types
BINARY_SENSOR_CALL_STATE = "call_state"
BINARY_SENSOR_MOTION = "motion"

# Event types
EVENT_DOORBELL = "doorbell"

# Logging
LOGGER_NAME = "custom_components.two_n_intercom"
