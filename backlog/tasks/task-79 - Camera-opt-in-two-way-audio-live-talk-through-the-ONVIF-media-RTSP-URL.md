---
id: TASK-79
title: 'Camera: opt-in two-way audio (live talk) through the ONVIF media RTSP URL'
status: To Test
assignee:
  - '@claude'
created_date: '2026-11-11 09:33'
updated_date: '2026-11-15 12:15'
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
- [x] #1 The camera step of the options flow has a two-way audio toggle, default off, stored in entry.options, with label and description in strings.json and translations en/de/cs [unit]
- [x] #2 With the toggle on, RTSP selected and a backchannel offered on the ONVIF media URL, stream_source() returns the ONVIF media URL with URL-encoded RTSP credentials and the entity declares CameraEntityCapabilities(two_way_audio=True) [unit]
- [x] #3 With the toggle off, or no backchannel on the ONVIF media URL, or a non-RTSP transport, stream_source() and the declared capabilities are identical to the behaviour before this task [unit]
- [x] #4 When homeassistant.components.camera has no CameraEntityCapabilities (Home Assistant older than 2026.11) the camera platform still sets up and the toggle has no effect [unit]
- [x] #5 The camera and the speaker media player use one shared backchannel probe result per setup; the RTSP password appears in no log record or diagnostics output [unit]
- [x] #6 README.md documents the toggle and the user-side requirements (Labs preview feature, HTTPS, WebRTC), replaces the "No live talk" limitation, and docs/API_REFERENCE.md and docs/ARCHITECTURE.md describe the stream source switch [unit]
- [ ] #7 E2E, when RTSP credentials are set in the E2E environment and the toggle is on: the HA camera stream source is the ONVIF media URL <-> the RTSP DESCRIBE of that URL offers a sendonly audio track [e2e]
- [ ] #8 With the toggle on, the dashboard camera shows the microphone and speech is audible on the real intercom; the live video still works [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. backchannel.py: BackchannelProbe (HA-free) runs the DESCRIBE search over the candidate URLs once and caches the result (url, track or error); the coordinator owns one instance (coordinator.backchannel_probe), so the speaker and the camera share it per setup.
2. media_player.py: setup reads the shared probe instead of its own search.
3. api.py: get_rtsp_onvif_url() (credential-free) and get_rtsp_onvif_url_with_credentials() (URL-encoded).
4. const.py + config_flow.py: option camera_two_way_audio (default off) in the camera step of the options flow, stored in entry.options; removed with the other camera options when the camera is disabled.
5. camera.py: guarded import of CameraEntityCapabilities; async_two_way_audio_available() = option on, capabilities class present, RTSP selected and resolved, probe found the track on the ONVIF media URL. Only then stream_source() returns the ONVIF media URL and the entity sets _attr_camera_entity_capabilities; otherwise nothing changes. New state attribute two_way_audio.
6. diagnostics.py: audio_backchannel block (credential-free URL, codec, error reason).
7. strings.json + translations en/de/cs, README, docs/API_REFERENCE.md, docs/ARCHITECTURE.md.
8. Unit tests (camera, probe, config flow, api, diagnostics, coordinator, translations) and a read-only E2E check.
Must not change: transport resolver, MJPEG path, dual HTTP auth, no secrets in logs/diagnostics (RTSP URL is the documented exception).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built on the TASK-78 working tree (not merged yet): the branch carries it as its first commit, rebased onto main. The backchannel search moved from media_player.py to backchannel.BackchannelProbe, owned by the coordinator.
Decisions: the camera switches only when the probe found the track on the ONVIF media URL (a track only on the classic path keeps the old source); the capabilities attribute is not set at all when two-way audio is inactive; new camera state attribute two_way_audio and diagnostics block audio_backchannel make the state visible (used by the E2E check).
Validation: unit suite 892 tests green in the E2E venv (locally one pre-existing import error, jinja2 missing for test_blueprint); validate.py green; e2e.sh wip passed (25 passed, 6 skipped). The two RTSP checks were skipped because the E2E environment has no RTSP account (E2E_RTSP_USER / E2E_RTSP_PASSWORD), so AC #7 is not proven. mypy and ruff are not installed locally and were not run. docs/architecture.excalidraw was not regenerated.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Opt-in two-way audio for the camera: option camera_two_way_audio (camera step, default off); with RTSP selected and the audio backchannel offered on the ONVIF media URL the camera streams from that URL and declares CameraEntityCapabilities(two_way_audio=True). Speaker and camera share one backchannel probe per setup (coordinator.backchannel_probe).

AC #1: proven - tests/test_config_flow.py test_camera_step_two_way_audio_toggle_defaults_off_and_is_saved, tests/test_translations.py test_camera_two_way_audio_option_is_translated (plus the existing key-consistency tests).
AC #2: proven - tests/test_camera.py test_toggle_on_with_backchannel_uses_onvif_url_and_declares_it, tests/test_api.py test_onvif_media_rtsp_urls.
AC #3: proven - tests/test_camera.py test_everything_else_keeps_the_previous_behaviour (toggle off/missing, no backchannel, backchannel only on the classic path, mjpeg, jpeg only, unresolved).
AC #4: proven - tests/test_camera.py test_module_loads_without_camera_entity_capabilities, test_old_home_assistant_ignores_the_toggle.
AC #5: proven - tests/test_backchannel.py BackchannelProbeTests (one DESCRIBE round for concurrent callers, password in no log record), tests/test_coordinator.py test_coordinator_owns_one_backchannel_probe_for_its_api, tests/test_camera.py test_setup_never_logs_the_rtsp_password, tests/test_diagnostics.py test_diagnostics_describe_backchannel_probe_without_credentials.
AC #6: proven - README.md (section Two-way audio (live talk), options table, Known Limitations), docs/API_REFERENCE.md and docs/ARCHITECTURE.md in the PR diff.
AC #7: unproven - e2e/tests/test_10_entities.py test_camera_two_way_audio_matches_rtsp_backchannel exists but was skipped: the E2E environment has no RTSP account and the staging entry has the toggle off.
AC #8: manual - Jan, on the real intercom.
<!-- SECTION:FINAL_SUMMARY:END -->
