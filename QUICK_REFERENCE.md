# Quick Reference Card

## 2N Intercom Integration - Door Type Selection

### Purpose
Allow users to select between Door (Dveře) and Gate (Vrata) types, which are properly exposed to HomeKit.

---

## Setup

### 1. Add Integration
**Settings** → **Devices & Services** → **Add Integration** → **2N Intercom**

### 2. Configure
| Field | Options | Description |
|-------|---------|-------------|
| **Name** | Text | Device name (e.g., "Front Door") |
| **Door Type** | Door / Gate | Type of door/gate |

### 3. Result
- Lock entity created: `lock.<device_name>`
- Available in HomeKit (if bridge configured)

---

## Door Type Behavior

### Door (Dveře)
- **HomeKit**: Lock accessory 🔒
- **Actions**: Lock / Unlock
- **Icon**: Lock symbol
- **Use for**: Regular doors, entrance doors

### Gate (Vrata)
- **HomeKit**: Garage Door Opener 🏠
- **Actions**: Open / Close
- **Icon**: Garage door symbol
- **Use for**: Gates, garage doors, large doors

---

## Changing Door Type

1. **Settings** → **Devices & Services**
2. Find **2N Intercom** integration
3. Click **Configure**
4. Select new **Door Type**
5. Click **Submit**
6. Integration reloads automatically

---

## HomeKit Setup

### Prerequisites
- Home Assistant HomeKit integration enabled
- Lock entity not excluded from HomeKit

### Verification
1. Open **Home** app on iOS/macOS
2. Find your device
3. Check accessory type matches door type

### Siri Commands

**For Doors:**
- "Hey Siri, unlock the front door"
- "Hey Siri, lock the front door"

**For Gates:**
- "Hey Siri, open the garden gate"
- "Hey Siri, close the garden gate"

---

## Translations

| English | Czech |
|---------|-------|
| Door Type | Typ dveří |
| Door | Dveře |
| Gate | Vrata |

---

## File Structure

```
custom_components/2n_intercom/
├── __init__.py           # Main integration
├── config_flow.py        # Configuration UI
├── const.py              # Constants (door types)
├── lock.py               # Lock entity (HomeKit mapping)
├── manifest.json         # Metadata
├── strings.json          # UI strings
└── translations/
    ├── cs.json          # Czech
    └── en.json          # English
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Integration not found | Check files in `config/custom_components/2n_intercom/` |
| Not in HomeKit | Verify HomeKit bridge is configured |
| Wrong accessory type | Change door type in options |
| Entity not updating | Reload integration |

---

## Technical Details

### Device Class Mapping
```python
if door_type == "gate":
    device_class = "gate"  # → Garage Door Opener
else:
    device_class = None     # → Lock
```

### Configuration Keys
- `CONF_DOOR_TYPE`: "door_type"
- `DOOR_TYPE_DOOR`: "door"
- `DOOR_TYPE_GATE`: "gate"

---

## Support

**Documentation:**
- README.md - Overview
- INSTALLATION.md - Detailed installation
- HOMEKIT_INTEGRATION.md - Technical details
- FLOW_DIAGRAM.md - Visual flow

**Validation:**
```bash
python3 validate.py
```

---

**Version**: 1.0.0  
**Domain**: `2n_intercom`  
**Platform**: `lock`  
**HomeKit**: ✓ Supported
