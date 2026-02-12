"""Constants for the 2N Intercom integration."""

DOMAIN = "twon_intercom"

# Configuration
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DOOR_TYPE = "door_type"

# Defaults
DEFAULT_PORT = 80

# Door types
DOOR_TYPE_DOOR = "door"
DOOR_TYPE_GATE = "gate"

DOOR_TYPES = [DOOR_TYPE_DOOR, DOOR_TYPE_GATE]

# Platforms
PLATFORMS = ["lock"]
