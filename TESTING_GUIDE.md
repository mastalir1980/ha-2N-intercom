# Testing Guide for 2N Intercom Integration

This guide helps test the 2N Intercom integration with a physical device.

## Prerequisites

- Home Assistant Core 2025+ running
- 2N IP Intercom device on network
- Network connectivity between HA and intercom
- 2N device credentials (username/password)
- iOS device with Home app (for HomeKit testing)

## Testing Checklist

### 1. Installation Testing

- [ ] Copy `custom_components/twon_intercom` to HA config directory
- [ ] Restart Home Assistant
- [ ] Check HA logs for loading errors
- [ ] Verify integration appears in Integration list

### 2. Connection Testing

**Manual API Test:**
```bash
# Test call status endpoint
curl -u username:password http://YOUR_IP/api/call/status

# Test snapshot endpoint
curl -u username:password http://YOUR_IP/api/camera/snapshot -o test.jpg

# Test relay control
curl -u username:password "http://YOUR_IP/api/switch/ctrl?switch=1&action=on"
```

**Expected Results:**
- Call status returns JSON with `{"success": true, "result": {...}}`
- Snapshot returns JPEG image
- Relay control returns success confirmation

### 3. Configuration Flow Testing

#### Step 1: Add Integration
- [ ] Go to Settings → Devices & Services
- [ ] Click "+ Add Integration"
- [ ] Search for "2N Intercom"
- [ ] Integration config flow starts

#### Step 2: Connection Configuration
Test these scenarios:

**Valid Credentials:**
- [ ] IP: `YOUR_DEVICE_IP`
- [ ] Port: `80`
- [ ] Protocol: `HTTP`
- [ ] Username: `valid_username`
- [ ] Password: `valid_password`
- [ ] Result: Proceeds to next step

**Invalid Credentials:**
- [ ] Use wrong password
- [ ] Result: Shows "cannot_connect" error

**Wrong IP:**
- [ ] Use non-existent IP
- [ ] Result: Shows "cannot_connect" error

**HTTPS Testing:**
- [ ] Protocol: `HTTPS`
- [ ] Port: Auto-changes to `443`
- [ ] Verify SSL: `Yes`
- [ ] Result: Works if device has valid cert

#### Step 3: Device Configuration
- [ ] Name: "Test Intercom"
- [ ] Enable Camera: `Yes`
- [ ] Enable Doorbell: `Yes`
- [ ] Number of Relays: `2`
- [ ] Proceeds to relay configuration

#### Step 4: Relay Configuration

**Relay 1 (Door):**
- [ ] Name: "Front Door"
- [ ] Number: `1`
- [ ] Type: `Door`
- [ ] Duration: `2000`

**Relay 2 (Gate):**
- [ ] Name: "Driveway Gate"
- [ ] Number: `2`
- [ ] Type: `Gate`
- [ ] Duration: `15000`

**Result:**
- [ ] Integration created successfully
- [ ] Shows success message
- [ ] Redirects to integration page

### 4. Entity Creation Testing

After setup completes, verify these entities exist:

**Camera Entity:**
- [ ] `camera.test_intercom_camera` exists
- [ ] State: `idle` or `streaming`
- [ ] Attributes include RTSP URL

**Binary Sensor Entity:**
- [ ] `binary_sensor.test_intercom_doorbell` exists
- [ ] Device class: `doorbell`
- [ ] State: `off` (when not ringing)

**Switch Entity:**
- [ ] `switch.test_intercom_front_door` exists
- [ ] State: `off`
- [ ] Can be toggled

**Cover Entity:**
- [ ] `cover.test_intercom_driveway_gate` exists
- [ ] State: `closed`
- [ ] Can be opened/closed

**Lock Entity (Legacy):**
- [ ] `lock.test_intercom_lock` exists
- [ ] State: `locked`
- [ ] Device class: none or "gate"

### 5. Camera Testing

**Snapshot Testing:**
- [ ] Open camera entity in HA
- [ ] Snapshot loads and displays
- [ ] Refresh snapshot works
- [ ] Check logs for snapshot API calls

**Stream Testing:**
```bash
# Test RTSP stream directly
ffplay rtsp://username:password@YOUR_IP/default
```

- [ ] Stream opens in media player
- [ ] Video is smooth (not choppy)
- [ ] Audio works (if supported)

**In Home Assistant:**
- [ ] Click on camera entity
- [ ] Click "Show video stream"
- [ ] Stream loads and plays
- [ ] Stream works on mobile app

### 6. Doorbell Testing

**Ring Detection:**
- [ ] Press doorbell button on intercom
- [ ] Binary sensor changes to `on`
- [ ] Sensor shows caller attributes
- [ ] Sensor auto-resets to `off` after ring ends

**Attributes Check:**
- [ ] `last_ring` timestamp is correct
- [ ] `call_state` shows "ringing" during ring
- [ ] Caller info populated (if available)

**Polling:**
- [ ] Enable debug logging
- [ ] Check coordinator polls every 5 seconds
- [ ] No excessive API calls

### 7. Door Relay Testing (Switch)

**Manual Control:**
- [ ] Click switch to turn on
- [ ] Switch turns on immediately
- [ ] Physical relay activates
- [ ] Switch auto-turns off after 2 seconds
- [ ] Door unlocks/opens

**Automation:**
```yaml
automation:
  - alias: "Test Door Open"
    trigger:
      platform: state
      entity_id: binary_sensor.test_doorbell
      to: 'on'
    action:
      service: switch.turn_on
      target:
        entity_id: switch.test_intercom_front_door
```

- [ ] Ring doorbell
- [ ] Automation triggers
- [ ] Door opens
- [ ] Switch resets correctly

### 8. Gate Relay Testing (Cover)

**Open Test:**
- [ ] Click "Open" in cover entity
- [ ] State changes to "opening"
- [ ] Physical relay activates
- [ ] State changes to "open" after duration
- [ ] Gate opens physically

**Close Test:**
- [ ] Click "Close"
- [ ] State changes to "closing"
- [ ] Relay activates
- [ ] State changes to "closed"
- [ ] Gate closes physically

**Timing:**
- [ ] Verify 15-second duration matches gate operation
- [ ] Adjust if needed in options

### 9. Options Flow Testing

- [ ] Go to integration
- [ ] Click "Configure"
- [ ] Options dialog opens
- [ ] Can toggle camera on/off
- [ ] Can toggle doorbell on/off
- [ ] Can change legacy door type
- [ ] Save changes
- [ ] Integration reloads
- [ ] Entities reflect changes

### 10. HomeKit Bridge Testing

**Setup:**
- [ ] HomeKit Bridge configured in HA
- [ ] 2N integration entities included

**Camera in HomeKit:**
- [ ] Open Home app on iOS
- [ ] Find intercom camera
- [ ] Tap to open
- [ ] Live stream works
- [ ] Snapshot shows

**Doorbell in HomeKit:**
- [ ] Camera shows doorbell icon
- [ ] Press physical doorbell
- [ ] iOS shows notification
- [ ] Notification includes snapshot
- [ ] Can view live feed from notification

**Door Switch:**
- [ ] Switch appears in Home app
- [ ] Tap to activate
- [ ] Door opens
- [ ] Status updates in Home app

**Gate Cover:**
- [ ] Gate appears as garage door
- [ ] Tap to open
- [ ] Shows "opening" status
- [ ] Shows "open" when complete
- [ ] Can close from Home app

### 11. Siri Testing

**Camera:**
- [ ] "Hey Siri, show me the front door camera"
- [ ] Camera stream appears on device

**Door:**
- [ ] "Hey Siri, turn on front door"
- [ ] Door opens

**Gate:**
- [ ] "Hey Siri, open the driveway gate"
- [ ] Gate opens
- [ ] "Hey Siri, is the gate open?"
- [ ] Siri reports status

### 12. Error Handling Testing

**Network Loss:**
- [ ] Disconnect intercom from network
- [ ] Entities become unavailable
- [ ] Coordinator retries with backoff
- [ ] Reconnect network
- [ ] Entities become available again

**Invalid Credentials:**
- [ ] Change password on device
- [ ] Entities become unavailable
- [ ] Error logged in HA
- [ ] Persistent notification shows

**API Errors:**
- [ ] Force API error (wrong endpoint)
- [ ] Error logged but doesn't crash
- [ ] Integration continues running

### 13. Performance Testing

**Resource Usage:**
- [ ] Check CPU usage (should be minimal)
- [ ] Check memory usage (stable, no leaks)
- [ ] Check network traffic (minimal polling)

**Responsiveness:**
- [ ] Switch response time < 1 second
- [ ] Camera snapshot < 2 seconds
- [ ] Stream startup < 3 seconds
- [ ] Doorbell detection < 5 seconds

**Long-term:**
- [ ] Run for 24 hours
- [ ] No memory leaks
- [ ] No connection failures
- [ ] No zombie processes

### 14. Multi-Device Testing

If you have multiple 2N devices:

- [ ] Add second integration
- [ ] Different name
- [ ] Both work independently
- [ ] No entity ID conflicts
- [ ] Both in HomeKit

### 15. Upgrade Testing

If upgrading from v1.0:

- [ ] Backup HA configuration
- [ ] Replace integration files
- [ ] Restart HA
- [ ] Legacy lock still works
- [ ] Can reconfigure for new features
- [ ] No automations broken

## Common Issues and Solutions

### Issue: Cannot Connect

**Symptoms:** "Failed to connect" error during setup

**Check:**
1. Ping device IP
2. Check port is correct (80 for HTTP)
3. Try curl command manually
4. Verify credentials
5. Check firewall rules

### Issue: Camera Not Streaming

**Symptoms:** Camera entity exists but no video

**Check:**
1. Test RTSP URL with VLC/ffplay
2. Enable RTSP on device
3. Check codec support (H.264)

### Issue: Doorbell Not Detecting

**Symptoms:** Ring doesn't trigger sensor

**Check:**
1. Enable debug logging
2. Check coordinator polling
3. Verify `/api/call/status` response during ring
4. Check call status attributes
5. Reduce polling interval if needed

### Issue: Relay Not Working

**Symptoms:** Switch/cover doesn't control relay

**Check:**
1. Verify relay number is correct
2. Test relay via web interface
3. Check credentials have permissions
4. Verify relay is enabled
5. Check pulse duration

### Issue: HomeKit Not Working

**Symptoms:** Entities not in Home app

**Check:**
1. HomeKit Bridge running
2. Entities included in bridge config
3. Device not in unavailable state
4. Bridge paired correctly
5. Try resetting bridge

## Debug Logging

Enable detailed logging in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.twon_intercom: debug
    custom_components.twon_intercom.api: debug
    custom_components.twon_intercom.coordinator: debug
    custom_components.twon_intercom.camera: debug
```

Restart HA and check logs during testing.

## Test Report Template

After testing, document results:

```markdown
# 2N Intercom Integration Test Report

**Date:** YYYY-MM-DD
**Tester:** Name
**Device:** 2N Model XYZ
**HA Version:** 2025.X.X

## Configuration
- IP: XXX.XXX.XXX.XXX
- Relays: 2 (1 door, 1 gate)
- Camera: Enabled
- Doorbell: Enabled

## Test Results

### Installation: ✅ Pass / ❌ Fail
- Notes:

### Configuration Flow: ✅ Pass / ❌ Fail
- Notes:

### Camera: ✅ Pass / ❌ Fail
- Snapshot: ✅/❌
- Stream: ✅/❌
- Notes:

### Doorbell: ✅ Pass / ❌ Fail
- Ring Detection: ✅/❌
- Attributes: ✅/❌
- Notes:

### Relays: ✅ Pass / ❌ Fail
- Door Switch: ✅/❌
- Gate Cover: ✅/❌
- Notes:

### HomeKit: ✅ Pass / ❌ Fail
- Camera: ✅/❌
- Doorbell: ✅/❌
- Controls: ✅/❌
- Siri: ✅/❌
- Notes:

## Issues Found
1. Issue description
   - Severity: High/Medium/Low
   - Steps to reproduce
   - Workaround

## Recommendations
- Suggestion 1
- Suggestion 2

## Conclusion
Overall: ✅ Pass / ❌ Fail / ⚠️ Conditional Pass
```

## Success Criteria

Integration passes testing if:

- ✅ All entities created correctly
- ✅ Camera streams and snapshots work
- ✅ Doorbell detects rings reliably
- ✅ Relays control doors/gates
- ✅ HomeKit integration functional
- ✅ No errors in normal operation
- ✅ Stable over 24+ hours
- ✅ Resource usage acceptable

## Next Steps After Testing

1. Document any issues found
2. Create GitHub issues for bugs
3. Update documentation based on findings
4. Share test report with maintainer
5. Provide feedback for improvements

---

**Need Help?**
- GitHub Issues: https://github.com/mastalir1980/ha-2N-intercom/issues
- Documentation: README.md, ARCHITECTURE.md
- HA Community: https://community.home-assistant.io/
