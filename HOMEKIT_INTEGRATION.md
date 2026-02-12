# Door Type Selection and HomeKit Integration

## Overview

This integration allows users to select between two door types:
- **Door** (Dveře) - Standard door lock
- **Gate** (Vrata) - Gate/garage door

The selection made by the user is automatically propagated to the HomeKit bridge, ensuring the correct accessory type is exposed in HomeKit.

## How It Works

### 1. Configuration Flow

When setting up the integration, users can select the door type via the configuration UI:

```python
# In config_flow.py
data_schema = vol.Schema({
    vol.Optional("name", default="2N Intercom"): cv.string,
    vol.Required(CONF_DOOR_TYPE, default=DOOR_TYPE_DOOR): vol.In(DOOR_TYPES),
})
```

### 2. Door Type Storage

The selected door type is stored in the config entry data and can be updated via options flow:

```python
# Users can change the door type later via integration options
class TwoNIntercomOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Allows updating door type after initial setup
        ...
```

### 3. HomeKit Device Class Mapping

The door type is mapped to the appropriate HomeKit device class in the lock entity:

```python
# In lock.py
def __init__(self, config_entry: ConfigEntry, door_type: str) -> None:
    if door_type == DOOR_TYPE_GATE:
        self._attr_device_class = "gate"
    # Door type has no device class (default lock behavior)
```

### 4. HomeKit Accessory Types

Home Assistant's HomeKit integration uses the device class to determine the accessory type:

- **Door** (no device_class): Exposed as **Lock** accessory in HomeKit
  - Appears as a standard door lock in the Home app
  - Shows locked/unlocked states
  - Can be locked/unlocked

- **Gate** (device_class="gate"): Exposed as **Garage Door Opener** accessory in HomeKit
  - Appears as a garage door in the Home app
  - Shows open/closed states
  - Can be opened/closed
  - More appropriate for gates and large doors

## User Experience

### Setup Flow

1. User adds the "2N Intercom" integration
2. User enters a name for the device
3. **User selects door type**: Door or Gate
4. Integration creates a lock entity with appropriate HomeKit configuration

### Changing Door Type

1. User goes to integration options
2. User selects new door type
3. Integration reloads with new configuration
4. HomeKit accessory updates to new type

### HomeKit Integration

Once the integration is set up and the HomeKit bridge is configured in Home Assistant:

1. The lock entity is automatically discovered by the HomeKit bridge
2. The device appears in the Home app with the correct accessory type
3. Users can control the door/gate from their iOS/macOS devices
4. Siri can control the door/gate using appropriate commands

## Technical Details

### HomeKit Bridge Declaration

The integration declares HomeKit support in `manifest.json`:

```json
{
  "domain": "twon_intercom",
  "homekit": {}
}
```

This tells Home Assistant that this integration is HomeKit-compatible.

### Device Class Values

- `None` (default): Standard lock
- `"gate"`: Gate/garage door opener

### Lock Entity Features

The lock entity supports:
- `LockEntityFeature.OPEN`: Allows opening the door/gate
- Locked/unlocked states
- Device information for proper identification in HomeKit

## Translations

The door type selection is translated in both English and Czech:

**English:**
- Door Type → "Door" or "Gate"

**Czech:**
- Typ dveří → "Dveře" nebo "Vrata"

## Example Configuration

### Example 1: Standard Door

```yaml
name: "Front Door"
door_type: "door"
```

Result in HomeKit: Lock accessory

### Example 2: Gate

```yaml
name: "Garden Gate"
door_type: "gate"
```

Result in HomeKit: Garage Door Opener accessory

## Future Enhancements

Potential future improvements:
- Add actual 2N API integration for real door control
- Support for multiple doors/gates per device
- Door state sensors (open/closed)
- Video doorbell support
- Call notification support
