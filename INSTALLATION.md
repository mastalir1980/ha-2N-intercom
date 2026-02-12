# Installation and Usage Guide

## Quick Start

### 1. Installation

Copy the integration to your Home Assistant configuration directory:

```bash
# Navigate to your Home Assistant config directory
cd /config

# Create custom_components directory if it doesn't exist
mkdir -p custom_components

# Copy the integration
cp -r /path/to/ha-2N-intercom/custom_components/twon_intercom custom_components/
```

### 2. Restart Home Assistant

After copying the files, restart Home Assistant to load the integration.

### 3. Add Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **2N Intercom**
4. Click on it to start the setup wizard

### 4. Configure Integration

**Setup Wizard:**

![Setup Wizard](docs/setup_wizard.png)

Fields:
- **Name**: Enter a name for your device (e.g., "Front Door", "Garden Gate")
- **Door Type**: Select the type:
  - **Door** (Dveře): For regular doors - will appear as a door lock in HomeKit
  - **Gate** (Vrata): For gates/garage doors - will appear as a garage door opener in HomeKit

Example configurations:

**For a front door:**
```
Name: Front Door
Door Type: Door
```

**For a gate:**
```
Name: Garden Gate
Door Type: Gate
```

### 5. Verify in Home Assistant

After setup, you should see:
- A lock entity named `lock.<your_device_name>`
- Device information in the Devices view
- The entity will show as "Locked" by default

### 6. HomeKit Integration

If you have the HomeKit integration enabled in Home Assistant:

1. The lock entity will automatically be available to HomeKit
2. Open the Home app on your iOS/macOS device
3. You should see your door/gate with the appropriate icon:
   - **Door type**: Lock icon 🔒
   - **Gate type**: Garage door icon 🏠

### 7. Using the Lock

**In Home Assistant:**
- Click the lock entity to unlock
- Click again to lock
- Use the "Open" button to trigger the door/gate opening

**In HomeKit:**
- For doors: Tap to lock/unlock
- For gates: Tap to open/close

**With Siri:**
- "Hey Siri, unlock the front door"
- "Hey Siri, open the garden gate"

## Changing Door Type

To change the door type after initial setup:

1. Go to **Settings** → **Devices & Services**
2. Find the **2N Intercom** integration
3. Click **Configure**
4. Select the new **Door Type**
5. Click **Submit**

The integration will reload with the new configuration, and the HomeKit accessory type will update accordingly.

## Troubleshooting

### Integration not appearing
- Ensure the files are in the correct location: `config/custom_components/twon_intercom/`
- Restart Home Assistant
- Check the logs for any errors

### HomeKit not showing the device
- Ensure HomeKit integration is set up in Home Assistant
- Check that the lock entity is not excluded from HomeKit
- Try restarting the HomeKit bridge

### Wrong accessory type in HomeKit
- Check the door type configuration in the integration options
- Change the door type and reload the integration
- Restart the HomeKit bridge

## Advanced Configuration

### Multiple Doors/Gates

You can add multiple instances of the integration for different doors:

1. Add the integration again
2. Give it a different name
3. Select the appropriate door type

Each instance will create a separate lock entity.

### Automation Examples

**Unlock when arriving home:**
```yaml
automation:
  - alias: "Unlock front door when arriving"
    trigger:
      - platform: zone
        entity_id: person.john
        zone: zone.home
        event: enter
    action:
      - service: lock.unlock
        target:
          entity_id: lock.front_door
```

**Open gate at specific times:**
```yaml
automation:
  - alias: "Open gate in the morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: lock.open
        target:
          entity_id: lock.garden_gate
```

## Development Status

This is a basic implementation that provides:
- ✅ Door type selection
- ✅ HomeKit integration
- ✅ Lock entity with open support
- ⏳ Real 2N API integration (planned)
- ⏳ Door state sensors (planned)
- ⏳ Video doorbell support (planned)

## Support

For issues or questions, please open an issue on the GitHub repository.
