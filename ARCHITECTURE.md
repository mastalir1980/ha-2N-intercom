# 2N Intercom Integration - Architecture Design

## Executive Summary

This document outlines the complete architecture for a Home Assistant custom integration for 2N IP intercoms, providing camera streaming, doorbell events, and relay control with full HomeKit compatibility.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Home Assistant Core                          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │           2N Intercom Integration (2n_intercom)            │ │
│  │                                                            │ │
│  │  ┌──────────────┐  ┌───────────────┐  ┌───────────────┐    │ │
│  │  │ Config Flow  │  │  Coordinator  │  │   API Client  │    │ │
│  │  │              │  │               │  │               │    │ │
│  │  │ - Setup UI   │  │ - Polling     │  │ - HTTP API    │  │ │
│  │  │ - Validation │  │ - Updates     │  │ - RTSP URLs   │  │ │
│  │  │ - Options    │  │ - Error       │  │ - Auth        │  │ │
│  │  └──────────────┘  │   handling    │  │ - Reconnect   │  │ │
│  │                    └───────┬───────┘  └───────┬───────┘  │ │
│  │                            │                   │          │ │
│  │  ┌─────────────────────────┴───────────────────┴───────┐ │ │
│  │  │                     Platforms                        │ │ │
│  │  │                                                      │ │ │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │ │ │
│  │  │  │  Camera  │  │ Binary   │  │ Switch / Cover   │  │ │ │
│  │  │  │          │  │ Sensor   │  │                  │  │ │ │
│  │  │  │ - Stream │  │          │  │ - Door (switch)  │  │ │ │
│  │  │  │ - Snap   │  │ - Ring   │  │ - Gate (cover)   │  │ │ │
│  │  │  └──────────┘  │ - Button │  │ - Multi-relay    │  │ │ │
│  │  │                │   filter │  └──────────────────┘  │ │ │
│  │  │                └──────────┘                        │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              HomeKit Bridge                            │ │
│  │                                                        │ │
│  │  - Camera (with doorbell button)                      │ │
│  │  - Doorbell service                                   │ │
│  │  - Lock or Garage Door Opener                         │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                       2N IP Intercom                             │
│                                                                  │
│  HTTP API:                                                       │
│  - /api/dir/query       (directory, caller info)                │
│  - /api/call/status     (call state, ringing)                   │
│  - /api/switch/ctrl     (relay control)                         │
│  - /api/camera/snapshot (JPEG snapshot)                         │
│                                                                  │
│  RTSP:                                                          │
│  - rtsp://user:pass@ip:port/stream                             │
│    (H.264 video + AAC audio)                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. File Structure

```
custom_components/2n_intercom/
├── __init__.py              # Integration setup, coordinator initialization
├── manifest.json            # Integration metadata, dependencies
├── const.py                 # Constants, configuration keys
├── config_flow.py           # Configuration UI and validation
├── api.py                   # 2N API client (NEW)
├── coordinator.py           # DataUpdateCoordinator (NEW)
├── camera.py                # Camera platform (NEW)
├── binary_sensor.py         # Doorbell platform (NEW)
├── switch.py                # Door relay control (NEW)
├── cover.py                 # Gate relay control (NEW)
├── lock.py                  # Legacy lock entity (KEEP for compatibility)
├── strings.json             # UI strings
└── translations/
    ├── en.json              # English
    └── cs.json              # Czech
```

### 2. API Client (`api.py`)

**Purpose**: Async HTTP client for 2N API communication

**Responsibilities**:
- HTTP/HTTPS connection management
- Authentication (Basic Auth)
- API endpoint abstraction
- Error handling and retry logic
- Session management
- SSL verification handling

**Key Methods**:
```python
class TwoNIntercomAPI:
    async def async_connect() -> bool
    async def async_get_directory() -> list[dict]
    async def async_get_call_status() -> dict
    async def async_switch_control(relay: int, action: str) -> bool
    async def async_get_snapshot() -> bytes
    def get_rtsp_url(profile: str = "default") -> str
```

**API Endpoint Mapping**:

| 2N API Endpoint | Method | Purpose | Returns |
|----------------|--------|---------|---------|
| `/api/dir/query` | GET | Get directory entries | JSON: caller names, numbers |
| `/api/call/status` | GET | Get call/ring status | JSON: state, caller_id, button |
| `/api/switch/ctrl?switch={n}&action={action}` | GET | Control relay | JSON: success status |
| `/api/camera/snapshot` | GET | Get JPEG snapshot | Binary: JPEG image |
| RTSP stream | - | Video stream URL | rtsp://host:port/stream |

### 3. DataUpdateCoordinator (`coordinator.py`)

**Purpose**: Central data management and polling

**Responsibilities**:
- Poll `/api/call/status` for doorbell events
- Update entity states
- Handle connection errors
- Provide data to all platforms
- Manage update intervals

**Update Strategy**:
- Normal polling: 5 seconds (for doorbell detection)
- Exponential backoff on errors
- Reconnect logic with configurable retries

**Data Structure**:
```python
@dataclass
class TwoNIntercomData:
    call_status: dict  # Current call state
    last_ring_time: datetime | None
    caller_info: dict | None
    available: bool
```

### 4. Configuration Flow (`config_flow.py`)

**Enhanced Configuration Steps**:

**Step 1: Connection**
- IP address (required)
- Port (default: 80 for HTTP, 443 for HTTPS)
- Protocol (HTTP/HTTPS dropdown)
- Username (required)
- Password (required)
- Verify SSL (checkbox, default: True)

**Step 2: Device Configuration**
- Device name (default: "2N Intercom")
- Enable camera (checkbox, default: True)
- Enable doorbell (checkbox, default: True)

**Step 3: Relay Configuration**
- Number of relays (dropdown: 1-4)
- For each relay:
  - Relay name
  - Device type (Door/Gate)
  - Relay number (1-4)

**Validation During Setup**:
1. Test HTTP connection
2. Verify credentials with `/api/call/status` call
3. Test camera snapshot if enabled
4. Validate RTSP URL format

**Options Flow**:
- Allow changing all configuration except IP/port
- Allow adding/removing relays
- Allow toggling camera/doorbell

### 5. Camera Platform (`camera.py`)

**Entity**: `camera.{device_name}_camera`

**Features**:
- Live RTSP H.264 stream
- Snapshot via `/api/camera/snapshot`
- HomeKit-compatible streaming
- Motion detection (via doorbell events)

**Implementation Strategy**:

**RTSP Streaming**:
- Use Home Assistant's generic camera stream component
- Provide RTSP URL: `rtsp://{username}:{password}@{ip}:{port}/{profile}`
- Support stream profile configuration
- WebRTC: Future enhancement via go2rtc integration

**Snapshot**:
- Fetch from `/api/camera/snapshot` endpoint
- Cache for 1 second to reduce API calls
- Use aiohttp for async fetching

**HomeKit Integration**:
- Mark as `supported_features = CameraEntityFeature.STREAM`
- Enable doorbell button via HomeKit service
- Link to binary_sensor for ring events

**WebRTC Future Path**:
- Phase 1: Use RTSP with HomeKit (current)
- Phase 2: Add go2rtc as optional dependency
- Phase 3: Provide WebRTC stream alongside RTSP
- Phase 4: Make WebRTC default with RTSP fallback

### 6. Binary Sensor Platform (`binary_sensor.py`)

**Entity**: `binary_sensor.{device_name}_doorbell`

**Device Class**: `doorbell`

**Features**:
- Ring event detection
- Optional directory entry filtering
- Optional button filtering (if 2N device has multiple buttons)
- Event attributes (caller name, button number, timestamp)

**Implementation**:
- Monitor coordinator data for call status changes
- Detect `state: "ringing"` in `/api/call/status`
- Set binary sensor to ON for ring duration
- Auto-off after ring stops or timeout (30 seconds)

**Attributes**:
```python
{
    "caller_name": "John Doe",  # From directory
    "button": 1,                # Button pressed
    "call_id": "123456",        # Call identifier
    "timestamp": "2026-02-19T12:00:00Z"
}
```

**Filtering**:
- Config option: Filter by directory entry
- Config option: Filter by button number
- Default: All rings trigger the sensor

**HomeKit Integration**:
- Exposed as doorbell service
- Triggers HomeKit doorbell notification
- Shows snapshot when ring occurs

### 7. Switch Platform (`switch.py`)

**Entity**: `switch.{device_name}_{relay_name}`

**Used For**: Doors (momentary action)

**Features**:
- Turn on = Unlock/open door
- Automatically turn off after action (momentary)
- Configurable pulse duration (default: 2 seconds)

**Implementation**:
- Call `/api/switch/ctrl?switch={relay}&action=on`
- Wait for configured duration
- Automatically set state to OFF
- Handle errors and timeouts

**HomeKit Integration**:
- Exposed as switch
- Can be used in scenes and automations
- Or linked to lock entity for compatibility

### 8. Cover Platform (`cover.py`)

**Entity**: `cover.{device_name}_{relay_name}`

**Used For**: Gates (longer action)

**Features**:
- Open/Close/Stop
- Position tracking (optional)
- Opening/Closing states
- Configurable open duration

**Implementation**:
- Open: Call `/api/switch/ctrl?switch={relay}&action=on`
- Track state: Opening → Open after duration
- Close: Similar logic
- Stop: Send stop command (if supported)

**Device Class**: `gate`

**HomeKit Integration**:
- Exposed as garage door opener
- Shows correct icon in Home app
- Natural Siri commands

### 9. Legacy Lock Platform (`lock.py`)

**Status**: Keep for backward compatibility

**Entity**: `lock.{device_name}_lock`

**Purpose**: 
- Maintain compatibility with existing installations
- Provide alternative control method
- Can be deprecated in future versions

## Entity Model

### Entity Creation Logic

Based on configuration, the following entities are created:

| Config | Entity Type | Entity ID | Created When |
|--------|------------|-----------|--------------|
| Camera enabled | Camera | `camera.{name}_camera` | Always if enabled |
| Doorbell enabled | Binary Sensor | `binary_sensor.{name}_doorbell` | Always if enabled |
| Relay 1 (Door) | Switch | `switch.{name}_{relay_name}` | Device type = Door |
| Relay 1 (Gate) | Cover | `cover.{name}_{relay_name}` | Device type = Gate |
| Relay 2-4 | Switch/Cover | `switch/cover.{name}_{relay_name}` | Based on type |
| Legacy | Lock | `lock.{name}_lock` | Optional compatibility |

### Device Info

All entities share common device info:

```python
{
    "identifiers": {(DOMAIN, config_entry.entry_id)},
    "name": config_entry.data["name"],
    "manufacturer": "2N",
    "model": "IP Intercom",
    "sw_version": "1.0.0",
    "configuration_url": f"http://{ip}",
}
```

## Configuration Constants

### Configuration Keys (`const.py`)

```python
# Domain
DOMAIN = "2n_intercom"

# Configuration keys
CONF_PROTOCOL = "protocol"  # "http" or "https"
CONF_VERIFY_SSL = "verify_ssl"
CONF_ENABLE_CAMERA = "enable_camera"
CONF_ENABLE_DOORBELL = "enable_doorbell"
CONF_RELAY_COUNT = "relay_count"
CONF_RELAYS = "relays"

# Relay configuration
CONF_RELAY_NAME = "relay_name"
CONF_RELAY_NUMBER = "relay_number"
CONF_RELAY_DEVICE_TYPE = "relay_device_type"
CONF_RELAY_PULSE_DURATION = "relay_pulse_duration"

# Device types
DEVICE_TYPE_DOOR = "door"
DEVICE_TYPE_GATE = "gate"

# Defaults
DEFAULT_PORT_HTTP = 80
DEFAULT_PORT_HTTPS = 443
DEFAULT_SCAN_INTERVAL = 5  # seconds
DEFAULT_PULSE_DURATION = 2  # seconds
DEFAULT_GATE_DURATION = 15  # seconds

# Platforms
PLATFORMS = ["camera", "binary_sensor", "switch", "cover", "lock"]
```

## HomeKit Integration

### Camera + Doorbell

**Strategy**: Combine camera and doorbell into single HomeKit accessory

**Implementation**:
- Camera entity with `CameraEntityFeature.STREAM`
- Binary sensor with `device_class: doorbell`
- HomeKit bridge automatically links them
- Ring events trigger HomeKit doorbell notification
- Snapshot shown on ring

**Configuration**:
- No special configuration needed
- HomeKit bridge automatically detects
- Accessory type: "Video Doorbell"

### Door vs Gate

**Door (Switch)**:
- Option 1: Expose switch directly
- Option 2: Create companion lock entity
- HomeKit shows as switch or lock
- Momentary action simulated

**Gate (Cover)**:
- Exposed as garage door opener
- Device class: `gate`
- HomeKit accessory type: "Garage Door Opener"
- Open/Close/Stop actions

### HomeKit Bridge Configuration

In Home Assistant configuration.yaml:

```yaml
homekit:
  - filter:
      include_domains:
        - camera
        - binary_sensor
        - cover
      include_entities:
        - switch.front_door  # If using switch for door
```

## Error Handling & Reconnect Logic

### Connection Errors

**Strategy**: Exponential backoff with max retries

```python
# In coordinator.py
async def _async_update_data():
    try:
        return await self.api.async_get_call_status()
    except (ConnectionError, TimeoutError) as err:
        if self._retry_count < MAX_RETRIES:
            self._retry_count += 1
            delay = min(2 ** self._retry_count, 60)  # Max 60s
            await asyncio.sleep(delay)
            raise UpdateFailed(f"Connection error: {err}")
        else:
            # Mark as unavailable
            raise ConfigEntryNotReady
```

### Authentication Errors

**Strategy**: Disable integration, require user intervention

```python
except AuthenticationError:
    # Notify user via persistent notification
    # Disable integration
    # Request reconfiguration
```

### API Errors

**Strategy**: Log and continue, mark entities unavailable

```python
except APIError as err:
    _LOGGER.warning("API error: %s", err)
    return None  # Entities become unavailable
```

## RTSP vs WebRTC

### Current Approach: RTSP

**Pros**:
- Simple integration
- Standard protocol
- Works with all 2N intercoms
- HomeKit compatible
- No additional dependencies

**Cons**:
- Higher latency (2-4 seconds)
- More bandwidth usage
- Less efficient encoding

**Implementation**:
- Use RTSP URL directly
- Let Home Assistant handle stream processing
- Compatible with HomeKit via HAP protocol

### Future Approach: WebRTC

**Pros**:
- Low latency (<1 second)
- Efficient bandwidth usage
- Better mobile support
- Modern protocol

**Cons**:
- Requires go2rtc or similar
- More complex setup
- May need transcoding
- Not all 2N models support it

**Migration Path**:

1. **Phase 1 (Current)**: RTSP only
   - Simple, reliable
   - Works everywhere

2. **Phase 2**: Add go2rtc support
   - Add `go2rtc` to manifest requirements
   - Detect if go2rtc is available
   - Use WebRTC if available, RTSP fallback

3. **Phase 3**: WebRTC preferred
   - Recommend go2rtc in documentation
   - Use WebRTC by default
   - Keep RTSP as fallback

4. **Phase 4**: WebRTC only (future)
   - When WebRTC is standard in HA
   - Remove RTSP code
   - Simplify implementation

**Code Structure for Future**:
```python
# camera.py
class TwoNIntercomCamera(Camera):
    async def stream_source(self):
        if self._use_webrtc and self._webrtc_available:
            return await self._get_webrtc_stream()
        else:
            return self._get_rtsp_stream()
```

## Known Pitfalls & Best Practices

### 1. Polling Interval

**Pitfall**: Too frequent polling can overload the intercom

**Best Practice**:
- Default: 5 seconds for doorbell detection
- Configurable in options
- Use coordinator to centralize polling
- Don't poll from individual entities

### 2. RTSP Stream Handling

**Pitfall**: Multiple stream requests can crash some intercoms

**Best Practice**:
- Let Home Assistant manage streams
- Don't create direct ffmpeg processes
- Use camera entity's built-in streaming
- One active stream at a time

### 3. Relay Control

**Pitfall**: Rapid relay toggling can damage hardware

**Best Practice**:
- Implement minimum delay between actions (1 second)
- Use cooldown period
- Log all relay actions
- Validate relay numbers

### 4. Authentication

**Pitfall**: Hardcoded credentials in logs

**Best Practice**:
- Use Home Assistant's credential storage
- Never log passwords
- Redact sensitive data in debug logs
- Use secrets in RTSP URLs

### 5. Error Messages

**Pitfall**: Generic errors confuse users

**Best Practice**:
- Specific error messages in config flow
- Translate error messages
- Provide troubleshooting hints
- Link to documentation

### 6. HomeKit Compatibility

**Pitfall**: Wrong device classes break HomeKit

**Best Practice**:
- Use correct device classes
- Test with actual HomeKit bridge
- Document HomeKit setup
- Provide troubleshooting guide

### 7. Multiple Intercoms

**Pitfall**: Entity ID conflicts

**Best Practice**:
- Use config entry ID in unique_id
- Allow multiple integrations
- Use descriptive names
- Support multi-device setup

### 8. Updates and Reload

**Pitfall**: Changes require HA restart

**Best Practice**:
- Implement options flow
- Use entry.add_update_listener()
- Reload integration on changes
- No restart required for most changes

### 9. Dependencies

**Pitfall**: Heavy dependencies increase load time

**Best Practice**:
- Minimal requirements in manifest
- Use built-in aiohttp
- No unnecessary libraries
- Consider optional dependencies (go2rtc)

### 10. Testing

**Pitfall**: Can't test without physical hardware

**Best Practice**:
- Create mock API for testing
- Use pytest-homeassistant-custom-component
- Unit tests for logic
- Integration tests with mock server

## Implementation Phases

### Phase 1: Foundation (Week 1)
- Create api.py with basic HTTP client
- Implement coordinator.py
- Update __init__.py with coordinator
- Basic error handling

### Phase 2: Configuration (Week 1)
- Expand config_flow.py
- Add validation
- Add options flow
- Update translations

### Phase 3: Camera (Week 2)
- Implement camera.py
- RTSP streaming
- Snapshot support
- Test HomeKit integration

### Phase 4: Doorbell (Week 2)
- Implement binary_sensor.py
- Ring detection
- Event attributes
- Test HomeKit notifications

### Phase 5: Relays (Week 3)
- Implement switch.py
- Implement cover.py
- Multiple relay support
- Test with physical device

### Phase 6: Testing & Documentation (Week 4)
- Comprehensive testing
- Update all documentation
- Create troubleshooting guide
- User acceptance testing

## Success Criteria

### Functional Requirements
- ✅ Camera streams via RTSP
- ✅ Snapshots work reliably
- ✅ Doorbell events trigger correctly
- ✅ Relay control works for all configured relays
- ✅ Config flow validates credentials
- ✅ Options flow allows configuration changes

### HomeKit Requirements
- ✅ Camera visible in Home app
- ✅ Doorbell notifications work
- ✅ Door relays work as locks or switches
- ✅ Gate relays work as garage door openers
- ✅ Siri voice control works
- ✅ Automation triggers work

### Quality Requirements
- ✅ No errors in HA logs during normal operation
- ✅ Proper error messages on failures
- ✅ Reconnects automatically after network issues
- ✅ No memory leaks or resource exhaustion
- ✅ Responsive UI (config flow completes in <5 seconds)

### Documentation Requirements
- ✅ README with installation instructions
- ✅ Configuration examples
- ✅ HomeKit setup guide
- ✅ Troubleshooting guide
- ✅ API documentation

## Conclusion

This architecture provides a robust, scalable foundation for 2N Intercom integration with Home Assistant. The design follows HA best practices, supports HomeKit integration, and provides a clear migration path to future technologies like WebRTC.

Key architectural decisions:
1. **DataUpdateCoordinator** for centralized state management
2. **RTSP first**, WebRTC-ready architecture
3. **Platform-based** entity organization
4. **Flexible relay** configuration (switch vs cover)
5. **HomeKit compatibility** as first-class citizen
6. **Comprehensive error handling** and reconnect logic

The implementation will be async-first, well-tested, and production-ready for Home Assistant Core 2025+.
