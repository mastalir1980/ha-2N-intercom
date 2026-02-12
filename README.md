# ha-2N-intercom

Home Assistant integration for 2N Intercom systems with HomeKit support.

## Features

- **Door/Gate Control**: Lock entity for controlling your 2N Intercom door or gate
- **HomeKit Integration**: Automatic HomeKit bridge support with proper device classification
- **Door Type Selection**: Choose between "Door" or "Gate" type during setup
  - **Door**: Exposed as a standard door lock in HomeKit
  - **Gate**: Exposed as a garage door (gate) accessory in HomeKit

## Installation

1. Copy the `custom_components/twon_intercom` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Configuration > Integrations
4. Click the "+ Add Integration" button
5. Search for "2N Intercom"
6. Follow the setup wizard and select your door type (Door or Gate)

## Configuration

During setup, you can configure:
- **Name**: The name for your 2N Intercom device
- **Door Type**: Choose "Door" for regular doors or "Gate" for gates/garage doors

The door type selection affects how the device is exposed to HomeKit:
- **Door**: Shows as a standard door lock in HomeKit
- **Gate**: Shows as a garage door accessory in HomeKit

You can change the door type later in the integration options.

## HomeKit Setup

After adding the integration, the lock entity will automatically be available to the HomeKit bridge if you have it configured. The device will appear in HomeKit with the appropriate accessory type based on your door type selection.

## Development

This is a custom integration for 2N Intercom systems. Contributions are welcome!
