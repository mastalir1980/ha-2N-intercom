"""Constants for the 2N Intercom integration."""

DOMAIN = "2n_intercom"

# Configuration keys
CONF_SERIAL_NUMBER = "serial_number"
CONF_PROTOCOL = "protocol"
CONF_VERIFY_SSL = "verify_ssl"
CONF_ENABLE_CAMERA = "enable_camera"
CONF_ENABLE_DOORBELL = "enable_doorbell"
# Opt-in flag for insecure transport: allow plaintext HTTP Basic-auth fallback.
# Default off so credentials are never sent in cleartext without consent.
CONF_ALLOW_INSECURE = "allow_insecure"
CONF_RING_ON_KEYPRESS = "ring_on_keypress"
CONF_RELAYS = "relays"
CONF_CALLED_ID = "called_id"
CALLED_ID_ALL = "__all__"
# Default directory user (UUID) for the grant_access service.
CONF_GRANT_ACCESS_USER = "grant_access_user"

# Form-only navigation control (never persisted): when the user submits a
# step with this checked, the flow returns to the previous step instead of
# advancing. HA data-entry flows have no native "Back" button.
CONF_GO_BACK = "go_back"

# General tuning keys
CONF_SCAN_INTERVAL = "scan_interval"

# Camera configuration keys
CONF_LIVE_VIEW_MODE = "live_view_mode"
CONF_MJPEG_WIDTH = "mjpeg_width"
CONF_MJPEG_HEIGHT = "mjpeg_height"
CONF_MJPEG_FPS = "mjpeg_fps"
CONF_CAMERA_SOURCE = "camera_source"
CONF_RTSP_USERNAME = "rtsp_username"
CONF_RTSP_PASSWORD = "rtsp_password"

# Relay configuration keys
CONF_RELAY_NAME = "relay_name"
CONF_RELAY_NUMBER = "relay_number"
CONF_RELAY_DEVICE_TYPE = "relay_device_type"
CONF_RELAY_PULSE_DURATION = "relay_pulse_duration"

# Device types
DEVICE_TYPE_DOOR = "door"
DEVICE_TYPE_GATE = "gate"

# Status LED is controlled by the intercom, not by the user.
IO_EXCLUDED_OUTPUTS = {"led_secured"}

# Protocols
PROTOCOL_HTTP = "http"
PROTOCOL_HTTPS = "https"
PROTOCOLS = [PROTOCOL_HTTP, PROTOCOL_HTTPS]

# Defaults
DEFAULT_PORT_HTTP = 80
DEFAULT_PORT_HTTPS = 443
DEFAULT_PROTOCOL = PROTOCOL_HTTPS
DEFAULT_VERIFY_SSL = False
DEFAULT_ALLOW_INSECURE = False
DEFAULT_ENABLE_CAMERA = True
DEFAULT_ENABLE_DOORBELL = True
DEFAULT_RING_ON_KEYPRESS = True
DEFAULT_SCAN_INTERVAL = 60  # seconds — events deliver real-time updates; polling is a safety net
SCAN_INTERVAL_MIN = 2  # seconds — below this we hammer the device for no benefit
SCAN_INTERVAL_MAX = 600  # seconds — events handle real-time; polling only needs to catch missed updates
DEFAULT_PULSE_DURATION = 2000  # milliseconds — door default
DEFAULT_GATE_DURATION = 15000  # milliseconds — gate default

# Camera live view modes
LIVE_VIEW_MODE_AUTO = "auto"
LIVE_VIEW_MODE_RTSP = "rtsp"
LIVE_VIEW_MODE_MJPEG = "mjpeg"
LIVE_VIEW_MODE_JPEG_ONLY = "jpeg_only"
LIVE_VIEW_MODES = [
    LIVE_VIEW_MODE_AUTO,
    LIVE_VIEW_MODE_RTSP,
    LIVE_VIEW_MODE_MJPEG,
    LIVE_VIEW_MODE_JPEG_ONLY,
]

# Camera transport defaults
DEFAULT_LIVE_VIEW_MODE = LIVE_VIEW_MODE_AUTO
DEFAULT_CAMERA_MJPEG_WIDTH = 1280
DEFAULT_CAMERA_MJPEG_HEIGHT = 960
DEFAULT_CAMERA_MJPEG_FPS = 10
DEFAULT_CAMERA_SOURCE = "internal"
CAMERA_SOURCES = ["internal", "external"]
CAMERA_MJPEG_FPS_MIN = 1
CAMERA_MJPEG_FPS_MAX = 15

# Access control — log events from the 2N HTTP API manual (5.10.1 api log
# caps). The coordinator subscribes only to the subset the device reports
# in /api/log/caps, because support depends on model, hardware and licence.
ACCESS_LOG_EVENTS = (
    "CardEntered",
    "CodeEntered",
    "MobKeyEntered",
    "FingerEntered",
    "UserAuthenticated",
    "UserRejected",
    "AccessTaken",
    "AccessBlocked",
    "AccessLimited",
    "ApiAccessRequested",
)
# Signals a directory change; used to invalidate the uuid -> name cache.
DIRECTORY_CHANGED_EVENT = "DirectoryChanged"

# Credential types exposed on parsed access events.
CREDENTIAL_CARD = "card"
CREDENTIAL_CODE = "code"
CREDENTIAL_MOBILE_KEY = "mobile_key"
CREDENTIAL_FINGERPRINT = "fingerprint"
CREDENTIAL_API = "api"

# /api/accesspoint/grantaccess access point ids.
ACCESS_POINT_ENTRY = 0
ACCESS_POINT_EXIT = 1
ACCESS_POINTS = (ACCESS_POINT_ENTRY, ACCESS_POINT_EXIT)

# Platforms — the actual platform list is built dynamically by
# ``__init__._get_platforms()`` based on whether the entry has relays
# configured. There is no static module-level PLATFORMS constant.
