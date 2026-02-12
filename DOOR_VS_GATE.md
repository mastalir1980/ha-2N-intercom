# Door vs Gate Comparison

## Visual Comparison in Apple Home App

### Door Type (Dveře)

```
┌─────────────────────────────────┐
│  🔒  Front Door                  │
│                                  │
│  ┌────────────────────────────┐ │
│  │                            │ │
│  │       LOCKED               │ │
│  │                            │ │
│  │   [  Tap to Unlock  ]      │ │
│  │                            │ │
│  └────────────────────────────┘ │
│                                  │
│  Accessory Type: Lock            │
│  State: Locked / Unlocked        │
│  Actions: Lock, Unlock           │
│                                  │
└─────────────────────────────────┘
```

**Characteristics:**
- Icon: Lock symbol 🔒
- States: Locked, Unlocked
- Actions: Lock, Unlock
- Behavior: Binary lock/unlock
- Use Case: Doors, entrance doors, interior doors

**Siri Commands:**
- "Unlock the front door"
- "Lock the front door"
- "Is the front door locked?"

---

### Gate Type (Vrata)

```
┌─────────────────────────────────┐
│  🏠  Garden Gate                 │
│                                  │
│  ┌────────────────────────────┐ │
│  │                            │ │
│  │       CLOSED               │ │
│  │                            │ │
│  │   [   Tap to Open   ]      │ │
│  │                            │ │
│  └────────────────────────────┘ │
│                                  │
│  Accessory Type: Garage Door     │
│  State: Open / Closed            │
│  Actions: Open, Close            │
│                                  │
└─────────────────────────────────┘
```

**Characteristics:**
- Icon: Garage door symbol 🏠
- States: Open, Closed, Opening, Closing
- Actions: Open, Close
- Behavior: Garage door style operation
- Use Case: Gates, garage doors, large doors

**Siri Commands:**
- "Open the garden gate"
- "Close the garden gate"
- "Is the garden gate open?"

---

## Technical Mapping

### Home Assistant Configuration

#### Door Configuration
```yaml
# Selected in UI
door_type: "door"

# Results in lock.py
device_class: None  # Default lock behavior
```

#### Gate Configuration
```yaml
# Selected in UI
door_type: "gate"

# Results in lock.py
device_class: "gate"  # Garage door behavior
```

### HomeKit Accessory Mapping

```python
# In Home Assistant's HomeKit integration

if entity.device_class == "gate":
    # Create Garage Door Opener accessory
    accessory_type = "GarageDoorOpener"
    services = [
        "CurrentDoorState",
        "TargetDoorState",
        "ObstructionDetected"
    ]
else:
    # Create Lock Mechanism accessory
    accessory_type = "LockMechanism"
    services = [
        "LockCurrentState",
        "LockTargetState"
    ]
```

---

## Feature Comparison

| Feature | Door (Lock) | Gate (Garage Door) |
|---------|-------------|-------------------|
| **HomeKit Service** | Lock Mechanism | Garage Door Opener |
| **Icon in Home app** | 🔒 Lock | 🏠 Garage |
| **Primary States** | Locked, Unlocked | Open, Closed |
| **Transitional States** | - | Opening, Closing |
| **Primary Actions** | Lock, Unlock | Open, Close |
| **Automation Triggers** | Lock state change | Position change |
| **Scenes Support** | ✓ | ✓ |
| **Siri Control** | ✓ | ✓ |
| **Watch App** | ✓ | ✓ |
| **Widget** | ✓ | ✓ |

---

## Use Case Recommendations

### Use Door Type For:
- ✅ Front doors
- ✅ Back doors
- ✅ Apartment entrance
- ✅ Interior doors
- ✅ Office doors
- ✅ Any door with a traditional lock

### Use Gate Type For:
- ✅ Driveway gates
- ✅ Garden gates
- ✅ Garage doors
- ✅ Barrier gates
- ✅ Large sliding doors
- ✅ Any door that "opens" rather than "unlocks"

---

## Configuration Examples

### Example 1: Apartment Building

```yaml
# Main entrance door
name: "Building Entrance"
door_type: door

# Apartment door
name: "Apartment 5B"
door_type: door
```

Result: Both show as locks 🔒 in Home app

### Example 2: Private House

```yaml
# Driveway gate
name: "Driveway Gate"
door_type: gate

# Front door
name: "Front Door"
door_type: door

# Garage door
name: "Garage"
door_type: gate
```

Result:
- Driveway Gate: Garage door 🏠
- Front Door: Lock 🔒
- Garage: Garage door 🏠

### Example 3: Commercial Building

```yaml
# Main entrance
name: "Main Entrance"
door_type: door

# Parking barrier
name: "Parking Barrier"
door_type: gate

# Office door
name: "Office 201"
door_type: door
```

Result:
- Main Entrance: Lock 🔒
- Parking Barrier: Garage door 🏠
- Office 201: Lock 🔒

---

## Automation Examples

### Lock Door When Leaving

```yaml
automation:
  - alias: "Lock doors when leaving"
    trigger:
      - platform: state
        entity_id: person.john
        to: "not_home"
    action:
      - service: lock.lock
        target:
          entity_id: lock.front_door
```

### Open Gate When Arriving

```yaml
automation:
  - alias: "Open gate when arriving"
    trigger:
      - platform: zone
        entity_id: device_tracker.car
        zone: zone.home
        event: enter
    action:
      - service: lock.open
        target:
          entity_id: lock.driveway_gate
```

### Close All at Night

```yaml
automation:
  - alias: "Secure home at night"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      # Lock all doors
      - service: lock.lock
        target:
          entity_id: 
            - lock.front_door
            - lock.back_door
      # Close all gates
      - service: lock.lock  # or lock.close
        target:
          entity_id:
            - lock.driveway_gate
            - lock.garden_gate
```

---

## Summary

The door type selection allows you to:

1. **Choose the right representation** for each access point
2. **Get appropriate HomeKit behavior** (lock vs garage door)
3. **Use natural language** with Siri
4. **See correct icons** in the Home app
5. **Create better automations** with meaningful actions

Select **Door** for traditional locks, **Gate** for opening barriers.
