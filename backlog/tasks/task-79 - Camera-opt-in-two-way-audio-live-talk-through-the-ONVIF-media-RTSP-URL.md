---
id: TASK-79
title: 'Camera: opt-in two-way audio (live talk) through the ONVIF media RTSP URL'
status: To Do
assignee: []
created_date: '2026-11-11 09:33'
labels:
  - audio
  - rtsp
  - camera
  - manual-close
milestone: m-1
dependencies:
  - TASK-78
references:
  - custom_components/2n_intercom/camera.py
  - custom_components/2n_intercom/media_player.py
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/config_flow.py
  - docs/API_REFERENCE.md
  - 'https://contributors.home-assistant.io/blog/2026/10/24/camera-two-way-audio/'
priority: medium
type: feature
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: users want to press the microphone button on the camera in the Home Assistant dashboard and talk to the visitor at the intercom.

Facts:
- Home Assistant 2026.11 added two-way audio for camera entities (developer blog 2026-10-24, "Two-way audio for camera entities"). An integration opts in with `_attr_camera_entity_capabilities = CameraEntityCapabilities(two_way_audio=True)` (import from homeassistant.components.camera, new in 2026.11). The frontend offers the microphone only when the entity declares it, the camera streams over WebRTC (natively or through a provider such as go2rtc; not HLS), the user enabled the preview feature "Two-way audio" under Settings > System > Labs, and Home Assistant is opened over HTTPS. The talk audio is sent over the RTSP ONVIF backchannel of the stream source.
- Verified by hand on the E2E intercom (fw 3.x): DESCRIBE with `Require: www.onvif.org/ver20/backchannel` on the classic paths (/h264_stream, /mjpeg_stream, /h265_stream) answers 551 Option not supported. On the ONVIF media URL `rtsp://<host>/onvif/media?transport=unicast&profile=profile_h264_hq` (Media2 GetStreamUri) it answers 200 and the SDP has an extra `m=audio 0 RTP/AVP 0`, PCMU/8000, a=sendonly track (control .../onvif/media/audioback); SETUP (RTP over TCP, interleaved), PLAY and TEARDOWN returned 200 and the device accepted PCMU RTP. Nothing had to be configured in the ONVIF profile.

Current behaviour: camera.py returns the /h264_stream URL from stream_source() and declares no camera capabilities, so the dashboard never shows the microphone.

Expected behaviour: a new option in the camera step of the options flow, off by default. When it is on, the live view transport is RTSP and the device offers the backchannel on the ONVIF media URL, stream_source() returns the ONVIF media URL (with the RTSP credentials, the documented exception for RTSP URLs) and the camera declares two_way_audio. In every other case the camera behaves exactly as today. On Home Assistant older than 2026.11 (CameraEntityCapabilities missing) the option has no effect and nothing fails.

Approach: reuse the backchannel probe added by TASK-78 (media_player.py `_async_find_backchannel`, api.py `get_rtsp_backchannel_endpoint` / `RTSP_ONVIF_PATH`); move the probe result to the coordinator so the camera and the speaker share one DESCRIBE at setup. New option key in const.py and entry.options (behaviour, not connection identity). Guard the import of CameraEntityCapabilities. Do not change the transport resolver or the MJPEG path.

Not known (hypotheses to be checked by Jan on the device): whether go2rtc negotiates the backchannel with this URL, whether the video on the ONVIF URL equals /h264_stream, and what happens when the speaker media player plays while somebody talks (the device serves at most 4 RTSP streams including the audio return channel).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The camera step of the options flow has a two-way audio toggle, default off, stored in entry.options, with label and description in strings.json and translations en/de/cs [unit]
- [ ] #2 With the toggle on, RTSP selected and a backchannel offered on the ONVIF media URL, stream_source() returns the ONVIF media URL with URL-encoded RTSP credentials and the entity declares CameraEntityCapabilities(two_way_audio=True) [unit]
- [ ] #3 With the toggle off, or no backchannel on the ONVIF media URL, or a non-RTSP transport, stream_source() and the declared capabilities are identical to the behaviour before this task [unit]
- [ ] #4 When homeassistant.components.camera has no CameraEntityCapabilities (Home Assistant older than 2026.11) the camera platform still sets up and the toggle has no effect [unit]
- [ ] #5 The camera and the speaker media player use one shared backchannel probe result per setup; the RTSP password appears in no log record or diagnostics output [unit]
- [ ] #6 README.md documents the toggle and the user-side requirements (Labs preview feature, HTTPS, WebRTC), replaces the "No live talk" limitation, and docs/API_REFERENCE.md and docs/ARCHITECTURE.md describe the stream source switch [unit]
- [ ] #7 E2E, when RTSP credentials are set in the E2E environment and the toggle is on: the HA camera stream source is the ONVIF media URL <-> the RTSP DESCRIBE of that URL offers a sendonly audio track [e2e]
- [ ] #8 With the toggle on, the dashboard camera shows the microphone and speech is audible on the real intercom; the live video still works [jan]
<!-- AC:END -->
