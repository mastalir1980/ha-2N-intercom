# ha-2N-intercom

Home Assistant custom integration for 2N IP Intercom systems with comprehensive features and HomeKit support.

## Features

### 🎥 Camera
- **Live RTSP video streaming** with H.264 codec
- **Snapshot support** via 2N HTTP API
- **HomeKit-compatible** video streaming

### 🔔 Doorbell
- **Ring event detection** from call status API
- **Binary sensor** with proper doorbell device class
- **Caller information** attributes (name, number, button)
- **HomeKit doorbell** notifications
- Event timestamps and call state tracking

### 🚪 Door/Gate Control
- **Switch entities** for doors (momentary relay action)
- **Cover entities** for gates (garage door opener style)
- **Multiple relay support** (up to 4 relays)
- **Configurable pulse duration** for each relay
- **HomeKit integration** with proper accessory types
  - Doors: Exposed as switches or locks
  - Gates: Exposed as garage door openers

### ⚙️ Configuration
- **Full UI-based configuration** (no YAML required)
- **Multi-step setup wizard**:
  1. Connection settings (IP, port, protocol, credentials)
  2. Device features (camera, doorbell)
  3. Relay configuration (per-relay device type and settings)
- **Options flow** for changing settings without re-setup
- **Credential validation** during setup

### 🏠 HomeKit Bridge Support
- Automatic device classification
- Camera with doorbell button
- Lock or garage door opener based on configuration
- Natural Siri voice commands

## Architecture

This integration uses modern Home Assistant best practices:

- **DataUpdateCoordinator** for centralized polling and state management
- **Async-first** implementation with aiohttp
- **Platform-based** architecture (camera, binary_sensor, switch, cover, lock)
- **Proper error handling** and automatic reconnection
- **Backward compatibility** with legacy lock entity

For detailed architecture information, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Manual

- Install and setup: [INSTALLATION.md](INSTALLATION.md)
- HomeKit details: [HOMEKIT_INTEGRATION.md](HOMEKIT_INTEGRATION.md)
- Quick reference: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- Release notes: [CHANGELOG.md](CHANGELOG.md)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add `https://github.com/mastalir1980/ha-2N-intercom` as an integration
6. Install "2N Intercom"
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/2n_intercom` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Configuration → Integrations
4. Click the "+ Add Integration" button
5. Search for "2N Intercom"

## Configuration

### Initial Setup

1. **Connection Settings**
   - IP Address: Your 2N intercom IP address
   - Port: HTTP port (default: 80) or HTTPS port (default: 443)
   - Protocol: HTTP or HTTPS
   - Username: 2N intercom username
   - Password: 2N intercom password
   - Verify SSL: Enable SSL certificate verification (HTTPS only)

2. **Device Features**
   - Name: Device name (default: "2N Intercom")
   - Enable Camera: Enable camera platform
   - Enable Doorbell: Enable doorbell binary sensor
   - Number of Relays: Select 0-4 relays to configure

3. **Relay Configuration** (for each relay)
   - Relay Name: Display name (e.g., "Front Door", "Garden Gate")
   - Relay Number: Physical relay number (1-4)
   - Device Type: 
     - **Door**: Creates switch entity (momentary action)
     - **Gate**: Creates cover entity (garage door style)
   - Pulse Duration: How long to activate relay (milliseconds)
     - Door default: 2000ms (2 seconds)
     - Gate default: 15000ms (15 seconds)

### Example Configurations

#### Apartment Building (Door Only)
```
Connection:
  - IP: 192.168.1.100
  - Port: 80
  - Protocol: HTTP
  - Username: admin
  - Password: ****

Device:
  - Name: Building Entrance
  - Enable Camera: Yes
  - Enable Doorbell: Yes
  - Number of Relays: 1

Relay 1:
  - Name: Entrance Door
  - Number: 1
  - Type: Door
  - Duration: 2000ms
```

Result:
- `camera.building_entrance_camera` - Live stream and snapshots
- `binary_sensor.building_entrance_doorbell` - Ring events
- `switch.building_entrance_entrance_door` - Door unlock

#### Private House (Door + Gate)
```
Connection:
  - IP: 192.168.1.101
  - Protocol: HTTPS
  - Username: admin
  - Password: ****

Device:
  - Name: Home Intercom
  - Enable Camera: Yes
  - Enable Doorbell: Yes
  - Number of Relays: 2

Relay 1:
  - Name: Front Door
  - Number: 1
  - Type: Door
  - Duration: 2000ms

Relay 2:
  - Name: Driveway Gate
  - Number: 2
  - Type: Gate
  - Duration: 15000ms
```

Result:
- `camera.home_intercom_camera`
- `binary_sensor.home_intercom_doorbell`
- `switch.home_intercom_front_door`
- `cover.home_intercom_driveway_gate`

## 2N API Endpoints Used

| Endpoint | Purpose | Platform |
|----------|---------|----------|
| `/api/call/status` | Monitor doorbell rings and call state | binary_sensor |
| `/api/dir/query` | Get caller directory information | binary_sensor |
| `/api/switch/ctrl` | Control relays (open door/gate) | switch, cover |
| `/api/camera/snapshot` | Get JPEG snapshot | camera |
| RTSP stream | Live video streaming | camera |

## HomeKit Integration

### Setup

1. Ensure Home Assistant HomeKit Bridge is configured
2. Add the 2N Intercom integration
3. Entities will automatically appear in HomeKit

### Accessory Types

- **Camera** → Video Doorbell (if doorbell enabled)
- **Binary Sensor** → Doorbell service
- **Switch (Door)** → Switch or Lock accessory
- **Cover (Gate)** → Garage Door Opener accessory

### Siri Commands

**Camera:**
- "Show me the front door camera"
- "What does the camera see?"

**Doorbell:**
- Ring events appear as HomeKit notifications

**Door (Switch):**
- "Turn on the front door" (triggers relay)
- "Open the front door"

**Gate (Cover):**
- "Open the driveway gate"
- "Close the driveway gate"
- "Is the gate open?"

## Troubleshooting

### Cannot Connect Error

**Symptoms:** "Failed to connect to the device" during setup

**Solutions:**
1. Verify IP address and port are correct
2. Check network connectivity to intercom
3. Verify username and password
4. Try HTTP instead of HTTPS if SSL verification fails
5. Check firewall rules

### Camera Not Streaming

**Symptoms:** Camera entity exists but no video

**Solutions:**
1. Verify RTSP stream is enabled on 2N intercom
2. Test RTSP URL manually: `rtsp://username:password@ip:554/h264_stream`
3. Check Home Assistant logs for stream errors

### Doorbell Not Triggering

**Symptoms:** Binary sensor not changing to "on" when doorbell rings

**Solutions:**
1. Verify doorbell is enabled in configuration
2. Check coordinator polling interval (default: 5 seconds)
3. Verify `/api/call/status` returns "ringing" state during ring
4. Check Home Assistant logs for API errors

### Relay Not Working

**Symptoms:** Switch/cover doesn't control relay

**Solutions:**
1. Verify relay number is correct (1-4)
2. Check relay is configured and enabled on 2N intercom
3. Test relay via 2N web interface
4. Verify credentials have permission to control relays
5. Check Home Assistant logs for API errors

### HomeKit Not Showing Entities

**Symptoms:** Entities visible in HA but not in Home app

**Solutions:**
1. Verify HomeKit Bridge is running
2. Check HomeKit Bridge includes the entities
3. Reset HomeKit Bridge and re-pair
4. Check entity is not in "unavailable" state

## Development

### Project Structure

```
custom_components/2n_intercom/
├── __init__.py              # Integration setup
├── api.py                   # 2N API client
├── coordinator.py           # DataUpdateCoordinator
├── config_flow.py           # Configuration UI
├── const.py                 # Constants
├── camera.py                # Camera platform
├── binary_sensor.py         # Doorbell platform
├── switch.py                # Door relay platform
├── cover.py                 # Gate relay platform
├── lock.py                  # Legacy lock platform
├── manifest.json            # Integration metadata
├── strings.json             # UI strings
└── translations/
    ├── en.json              # English
    └── cs.json              # Czech
```

### Testing

To test the integration:

1. Install in development mode
2. Check Home Assistant logs for any errors
3. Test all features (camera, doorbell, relays)

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Version History

### 1.0.0 (Current)
- Initial public release
- Camera platform with RTSP streaming
- Doorbell binary sensor
- Switch platform for doors
- Cover platform for gates
- DataUpdateCoordinator-based polling
- Full config flow with multi-step wizard
- HomeKit support

## License

This project is open source. See [LICENSE](LICENSE).

## Credits

Created for the Home Assistant community
Developed by: mastalir1980

## Support

For issues, questions, or feature requests, please:
- Open an issue on GitHub
- Check existing documentation
- Review troubleshooting section
