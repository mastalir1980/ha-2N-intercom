#!/usr/bin/env python3
"""
Static validation for the 2N Intercom integration.

Catches the regression classes that the unit tests don't:

1. Required files are present (manifest, platforms, services, translations).
2. JSON files parse cleanly.
3. ``manifest.json`` meets HA 2026.4+ expectations
   (no bundled requirements, ``iot_class=local_push``,
   ``integration_type=device``, ``config_flow`` set, ``version`` set).
4. ``hacs.json`` targets a supported HA version.
5. HomeKit auto-discovery is still declared.
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
COMPONENT_DIR = BASE_DIR / "custom_components" / "2n_intercom"


def check_file_exists(filepath: Path, description: str) -> bool:
    """Check if a file exists."""
    if filepath.exists():
        print(f"✓ {description}: {filepath.name}")
        return True
    print(f"✗ {description} missing: {filepath}")
    return False


def check_json_valid(filepath: Path) -> bool:
    """Check if a JSON file is valid."""
    try:
        with open(filepath) as f:
            json.load(f)
        print(f"✓ Valid JSON: {filepath.name}")
        return True
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in {filepath}: {e}")
        return False


def check_homekit_in_manifest() -> bool:
    """Check if HomeKit auto-discovery is declared in manifest.json."""
    manifest_file = COMPONENT_DIR / "manifest.json"
    with open(manifest_file) as f:
        manifest = json.load(f)

    if "homekit" in manifest:
        print("✓ HomeKit auto-discovery declared in manifest.json")
        return True
    print("✗ HomeKit auto-discovery not declared in manifest.json")
    return False


def check_manifest_compliance() -> bool:
    """Check that manifest.json meets HA 2026.4+ expectations.

    Catches the regression class of M7: bundled deps reappearing,
    iot_class drifting back to ``local_polling``, integration_type
    going missing, etc.
    """
    manifest_file = COMPONENT_DIR / "manifest.json"
    with open(manifest_file) as f:
        manifest = json.load(f)

    ok = True

    if manifest.get("requirements", []) != []:
        print(
            f"✗ manifest.requirements must be empty (HA core ships aiohttp); "
            f"got {manifest.get('requirements')!r}"
        )
        ok = False
    else:
        print("✓ manifest.requirements is empty")

    iot_class = manifest.get("iot_class")
    if iot_class != "local_push":
        print(
            f"✗ manifest.iot_class must be 'local_push' "
            f"(integration uses log subscription); got {iot_class!r}"
        )
        ok = False
    else:
        print("✓ manifest.iot_class is local_push")

    integration_type = manifest.get("integration_type")
    if integration_type != "device":
        print(
            f"✗ manifest.integration_type must be 'device'; got {integration_type!r}"
        )
        ok = False
    else:
        print("✓ manifest.integration_type is device")

    if not manifest.get("config_flow"):
        print("✗ manifest.config_flow must be true")
        ok = False
    else:
        print("✓ manifest.config_flow is true")

    if not manifest.get("version"):
        print("✗ manifest.version is missing")
        ok = False
    else:
        print(f"✓ manifest.version is {manifest['version']}")

    return ok


def check_hacs_min_ha_version() -> bool:
    """Check that hacs.json points at the supported HA version."""
    hacs_file = BASE_DIR / "hacs.json"
    if not hacs_file.exists():
        print("✗ hacs.json missing")
        return False
    with open(hacs_file) as f:
        hacs = json.load(f)
    min_version = hacs.get("homeassistant")
    if not min_version or not min_version.startswith("2026."):
        print(
            f"✗ hacs.json homeassistant must target 2026.x or newer; "
            f"got {min_version!r}"
        )
        return False
    print(f"✓ hacs.json targets HA {min_version}")
    return True


def main() -> int:
    """Run all checks."""
    print("=" * 60)
    print("2N Intercom Integration Validation")
    print("=" * 60)

    all_passed = True

    # Check required files
    print("\n1. Checking required files...")
    required_files = [
        (COMPONENT_DIR / "__init__.py", "Integration entry point"),
        (COMPONENT_DIR / "manifest.json", "Manifest"),
        (COMPONENT_DIR / "const.py", "Constants"),
        (COMPONENT_DIR / "config_flow.py", "Config / reauth / reconfigure flows"),
        (COMPONENT_DIR / "coordinator.py", "DataUpdateCoordinator"),
        (COMPONENT_DIR / "api.py", "Async 2N HTTP client"),
        (COMPONENT_DIR / "entity.py", "Shared entity base"),
        (COMPONENT_DIR / "camera.py", "Camera platform (MjpegCamera)"),
        (COMPONENT_DIR / "binary_sensor.py", "Doorbell + IO + relay-active sensors"),
        (COMPONENT_DIR / "sensor.py", "SIP / call diagnostic sensors"),
        (COMPONENT_DIR / "switch.py", "Door relay switch platform"),
        (COMPONENT_DIR / "cover.py", "Gate relay cover platform"),
        (COMPONENT_DIR / "services.yaml", "Service definitions"),
        (COMPONENT_DIR / "strings.json", "UI strings"),
        (COMPONENT_DIR / "translations" / "en.json", "English translations"),
        (COMPONENT_DIR / "translations" / "cs.json", "Czech translations"),
        (COMPONENT_DIR / "translations" / "de.json", "German translations"),
    ]

    for filepath, description in required_files:
        if not check_file_exists(filepath, description):
            all_passed = False

    # Check JSON files
    print("\n2. Validating JSON files...")
    json_files = [
        COMPONENT_DIR / "manifest.json",
        COMPONENT_DIR / "strings.json",
        COMPONENT_DIR / "translations" / "en.json",
        COMPONENT_DIR / "translations" / "cs.json",
        COMPONENT_DIR / "translations" / "de.json",
        BASE_DIR / "hacs.json",
    ]

    for filepath in json_files:
        if not check_json_valid(filepath):
            all_passed = False

    # Check manifest content for HA 2026.4+ compliance
    print("\n3. Checking manifest compliance...")
    if not check_manifest_compliance():
        all_passed = False

    # Check HomeKit auto-discovery
    print("\n4. Checking HomeKit declaration...")
    if not check_homekit_in_manifest():
        all_passed = False

    # Check HACS metadata
    print("\n5. Checking HACS metadata...")
    if not check_hacs_min_ha_version():
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All checks passed! Integration is properly configured.")
        print("\nKey features:")
        print("  • Native MJPEG live view (no ffmpeg) with RTSP fallback")
        print("  • Event-driven state updates with backup polling safety net")
        print("  • answer_call / hangup_call / grant_access services targeting a config entry")
        print("  • Real-state diagnostic sensors (SIP, call state, IO, relay)")
        print("  • Reauth and reconfigure flows (HA 2026.4+ compliant)")
        print("  • Switch + cover relay entities")
        print("  • HomeKit bridge auto-discovery")
        print("  • Czech, English, and German translations")
        return 0
    print("✗ Some checks failed. Please review the output above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
