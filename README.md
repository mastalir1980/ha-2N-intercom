# 2N Intercom Integration for Home Assistant

A custom integration for Home Assistant to control and monitor 2N IP intercom devices.

## Features

This integration provides the following entities:

### Switches
- **Camera** - Enable/disable the intercom camera
- **Microphone** - Enable/disable the intercom microphone
- **Auto Open** - Enable/disable automatic door opening

### Binary Sensors
- **Call State** - Indicates if there's an active call
- **Motion** - Detects motion at the intercom

### Camera
- **Camera Snapshot** - View live snapshots from the intercom camera

### Events
- **Doorbell** - Triggered when the doorbell is pressed

## Installation

### HACS (Recommended)
1. Add this repository as a custom repository in HACS
2. Search for "2N Intercom" in HACS
3. Click "Install"
4. Restart Home Assistant

### Manual Installation
1. Copy the `custom_components/two_n_intercom` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "2N Intercom"
4. Enter your device details:
   - **Host**: IP address or hostname of your 2N intercom
   - **Username**: (Optional) Username for authentication
   - **Password**: (Optional) Password for authentication
   - **Poll Interval**: Polling interval in seconds (default: 30)

## API Endpoints

This integration uses the following API endpoints (based on the Homebridge plugin):
- `/api/system/status` - System status information
- `/api/switch/caps` - Available switches and their capabilities
- `/api/switch/ctrl` - Control switches
- `/api/call/status` - Call status information
- `/api/camera/snapshot` - Camera snapshot

## Requirements

- Home Assistant 2024.1.0 or newer
- 2N IP intercom device with API access
- Network connectivity to the intercom device

## Support

For issues, questions, or feature requests, please visit the [GitHub repository](https://github.com/mastalir1980/ha-2N-intercom/issues).

## License

This project is licensed under the MIT License.
