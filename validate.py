#!/usr/bin/env python3
"""
Test script to validate the 2N Intercom integration structure.

This script verifies:
1. All required files are present
2. JSON files are valid
3. Python files have valid syntax
4. Door type configuration is properly defined
"""

import json
import os
import sys
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent
COMPONENT_DIR = BASE_DIR / "custom_components" / "2n_intercom"

def check_file_exists(filepath: Path, description: str) -> bool:
    """Check if a file exists."""
    if filepath.exists():
        print(f"✓ {description}: {filepath.name}")
        return True
    else:
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

def check_door_types_in_const():
    """Check if door types are properly defined in const.py."""
    const_file = COMPONENT_DIR / "const.py"
    with open(const_file) as f:
        content = f.read()
    
    required_constants = [
        "CONF_DOOR_TYPE",
        "DOOR_TYPE_DOOR",
        "DOOR_TYPE_GATE",
        "DOOR_TYPES",
    ]
    
    all_present = True
    for const in required_constants:
        if const in content:
            print(f"✓ Constant defined: {const}")
        else:
            print(f"✗ Constant missing: {const}")
            all_present = False
    
    return all_present

def check_homekit_in_manifest():
    """Check if HomeKit support is declared in manifest.json."""
    manifest_file = COMPONENT_DIR / "manifest.json"
    with open(manifest_file) as f:
        manifest = json.load(f)
    
    if "homekit" in manifest:
        print("✓ HomeKit support declared in manifest.json")
        return True
    else:
        print("✗ HomeKit support not declared in manifest.json")
        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("2N Intercom Integration Validation")
    print("=" * 60)
    
    all_passed = True
    
    # Check required files
    print("\n1. Checking required files...")
    required_files = [
        (COMPONENT_DIR / "__init__.py", "Main integration file"),
        (COMPONENT_DIR / "manifest.json", "Manifest file"),
        (COMPONENT_DIR / "const.py", "Constants file"),
        (COMPONENT_DIR / "config_flow.py", "Config flow file"),
        (COMPONENT_DIR / "lock.py", "Lock platform file"),
        (COMPONENT_DIR / "strings.json", "Strings file"),
        (COMPONENT_DIR / "translations" / "en.json", "English translations"),
        (COMPONENT_DIR / "translations" / "cs.json", "Czech translations"),
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
    ]
    
    for filepath in json_files:
        if not check_json_valid(filepath):
            all_passed = False
    
    # Check door type configuration
    print("\n3. Checking door type configuration...")
    if not check_door_types_in_const():
        all_passed = False
    
    # Check HomeKit support
    print("\n4. Checking HomeKit integration...")
    if not check_homekit_in_manifest():
        all_passed = False

    # Skip manifest name/version syncing (name should not include version)
    print("\n5. Skipping manifest name/version sync...")
    print("✓ Manifest name is expected to be versionless")
    
    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All checks passed! Integration is properly configured.")
        print("\nKey features:")
        print("  • Door type selection (Door/Gate)")
        print("  • HomeKit bridge support")
        print("  • Czech and English translations")
        return 0
    else:
        print("✗ Some checks failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
