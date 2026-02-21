"""Constants for the 2N Intercom integration."""

DOMAIN = "2n_intercom"

# Configuration keys
CONF_PROTOCOL = "protocol"
CONF_VERIFY_SSL = "verify_ssl"
CONF_ENABLE_CAMERA = "enable_camera"
CONF_ENABLE_DOORBELL = "enable_doorbell"
CONF_RELAY_COUNT = "relay_count"
CONF_RELAYS = "relays"
CONF_DOOR_TYPE = "door_type"

# Relay configuration keys
CONF_RELAY_NAME = "relay_name"
CONF_RELAY_NUMBER = "relay_number"
CONF_RELAY_DEVICE_TYPE = "relay_device_type"
CONF_RELAY_PULSE_DURATION = "relay_pulse_duration"

# Device types
DEVICE_TYPE_DOOR = "door"
DEVICE_TYPE_GATE = "gate"

# Legacy door types (for backward compatibility)
DOOR_TYPE_DOOR = "door"
DOOR_TYPE_GATE = "gate"
DOOR_TYPES = [DOOR_TYPE_DOOR, DOOR_TYPE_GATE]

# Protocols
PROTOCOL_HTTP = "http"
PROTOCOL_HTTPS = "https"
PROTOCOLS = [PROTOCOL_HTTP, PROTOCOL_HTTPS]

# Defaults
DEFAULT_PORT_HTTP = 80
DEFAULT_PORT_HTTPS = 443
DEFAULT_PROTOCOL = PROTOCOL_HTTPS
DEFAULT_VERIFY_SSL = False
DEFAULT_ENABLE_CAMERA = True
DEFAULT_ENABLE_DOORBELL = True
DEFAULT_RELAY_COUNT = 1
DEFAULT_SCAN_INTERVAL = 5  # seconds
DEFAULT_PULSE_DURATION = 2000  # milliseconds
DEFAULT_GATE_DURATION = 15000  # milliseconds

# Platforms
PLATFORMS = ["camera", "binary_sensor", "switch", "cover", "lock"]
