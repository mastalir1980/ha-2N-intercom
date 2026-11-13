---
id: TASK-78
title: >-
  Speaker media_player: play audio on the intercom over the RTSP audio
  backchannel
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-10 14:30'
updated_date: '2026-11-11 09:33'
labels:
  - audio
  - rtsp
  - media-player
  - manual-close
milestone: m-1
dependencies: []
references:
  - custom_components/2n_intercom/camera.py
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/__init__.py
  - docs/API_REFERENCE.md
  - 'https://www.onvif.org/specs/stream/ONVIF-Streaming-Spec.pdf'
priority: medium
type: feature
ordinal: 84000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: the integration already shows RTSP video (camera.py, live view mode rtsp), but Home Assistant has no way to send sound to the intercom. Users want announcements and TTS at the door from automations ("Please wait, somebody is coming").

Current behaviour: no entity or service plays audio on the device. README lists two-way audio as out of scope.

Expected behaviour: a media_player entity (device class speaker) on the intercom device. media_player.play_media (URL, media-source item, TTS, announce) plays the sound on the intercom speaker. The integration opens its own RTSP session to the device RTSP server with the ONVIF audio backchannel (ONVIF Streaming Specification, chapter "Audio backchannel": DESCRIBE/SETUP/PLAY carry the header Require: www.onvif.org/ver20/backchannel, the backchannel media section in the SDP is marked a=sendonly), transcodes the source with the ffmpeg binary of Home Assistant to the offered codec (G.711 PCMU or PCMA, 8 kHz mono) and sends RTP packets interleaved on the RTSP TCP connection. It uses the RTSP credentials already stored in entry.options (the 2N RTSP server has its own user database) and Digest authentication.

Evidence: the 2N configuration manual (Services > Streaming) documents the audio return channel on the RTSP server ("Fix defective audio backchannel" setting; the limit of 4 RTSP streams counts the audio return channel). Which codecs and tracks the E2E intercom (fw 3.x) offers in the SDP is not verified yet: the device was not reachable when the task was written. That is a hypothesis until the E2E check below runs.

Out of scope: live talk from a browser microphone (the HA frontend has no microphone support; that needs go2rtc and a third-party card), volume control, changes to the camera transport.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A media_player entity with translation key speaker is created on the intercom device only when RTSP credentials are configured, the RTSP probe succeeded and the DESCRIBE answer with the backchannel Require header contains a sendonly audio track with PCMU or PCMA; otherwise no entity is created and setup of the other platforms is unaffected [unit]
- [ ] #2 play_media runs DESCRIBE, SETUP (RTP/AVP/TCP interleaved) and PLAY with the backchannel Require header and Digest authentication, sends the transcoded audio as 20 ms RTP packets with the payload type from the SDP in real time, and ends with TEARDOWN; the entity state is playing while audio is sent and idle afterwards [unit]
- [ ] #3 media-source items (incl. TTS) and relative URLs are resolved to a playable URL before transcoding; media_stop and a second play_media stop the running playback and close its RTSP session [unit]
- [ ] #4 Rejected credentials, a missing backchannel track, an unsupported codec, an ffmpeg failure or a lost connection raise a translated HomeAssistantError or are logged, leave the entity idle, and never write the RTSP password or a URL with credentials to the log [unit]
- [ ] #5 strings.json, translations en/de/cs and icons.json contain the speaker entity and the new error messages; the translation consistency test passes [unit]
- [ ] #6 README.md (feature, setup, limitations), docs/API_REFERENCE.md (RTSP backchannel handshake) and docs/ARCHITECTURE.md describe the speaker entity [unit]
- [ ] #7 E2E, when RTSP credentials are set in the E2E environment: HA has the speaker media_player entity in state idle <-> the RTSP DESCRIBE of the intercom with the backchannel Require header offers a sendonly audio track [e2e]
- [ ] #8 A sound played with media_player.play_media (and a TTS announcement) is audible on the speaker of the real intercom [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. backchannel.py (new, no HA imports): RTSP client for the ONVIF audio backchannel - DESCRIBE/SETUP/PLAY/TEARDOWN with the Require header, Digest (MD5) with increasing nc, SDP parser for the sendonly PCMU/PCMA track, real-time RTP G.711 over the interleaved TCP connection, GET_PARAMETER keep-alive.
2. media_player.py (new): TwoNIntercomSpeaker on TwoNIntercomEntity; setup probes DESCRIBE once and creates the entity only when a track is offered; play_media resolves media-source/relative URLs, accepts only http/https, starts HA ffmpeg (protocol whitelist, raw G.711 8 kHz mono), streams in a config-entry background task; media_stop / new play / removal release the RTSP session and ffmpeg.
3. __init__.py: media_player platform only when both RTSP options are set. api.py: get_rtsp_endpoint() (credential-free URL). manifest.json: after_dependencies ffmpeg, media_source (no new requirement).
4. strings.json, translations en/de/cs, icons.json: speaker entity + five error messages.
5. Unit tests against a loopback fake RTSP server (tests/_rtsp_fake.py): test_backchannel.py, test_media_player.py, platform selection in test_init.py.
6. E2E: e2elib/rtsp.py (independent DESCRIBE helper) + read-only test_speaker_matches_rtsp_backchannel, skipped without E2E_RTSP_USER/E2E_RTSP_PASSWORD.
7. Docs: README, docs/API_REFERENCE.md, docs/ARCHITECTURE.md, code maps in CLAUDE.md and .github/copilot-instructions.md.
Must not change: camera transport selection, dual HTTP auth in api.py, no secrets in URLs/logs (the RTSP password is used only for Digest responses).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on branch task-78-speaker-rtsp-backchannel (worktree, not committed yet). Unit suite: 845 of 846 pass; the one error is the pre-existing import of jinja2 in test_blueprint on this machine (same on main). validate.py green.
Not verified on a device: the E2E intercom did not answer from the development machine (no port reachable) and no RTSP account is in the E2E environment yet, so e2e.sh wip and the new E2E check were not run. Open device questions: codecs/tracks in the SDP on fw 3.x, whether SETUP of only the backchannel track is accepted, behaviour during an active call.
Found and fixed while testing: a playback task cancelled before its first step never ran its cleanup and left the RTSP connection and ffmpeg open; cleanup no longer depends on the task.
Not done: docs/architecture.excalidraw was not regenerated; mypy was not run (not installed locally).

Update after a manual check on the E2E intercom (fw 3.x): the classic stream paths answer 551 Option not supported to the backchannel Require header; the backchannel (PCMU/8000, a=sendonly, control .../onvif/media/audioback) is offered only on the ONVIF media URL rtsp://<host>/onvif/media?transport=unicast&profile=profile_h264_hq, where SETUP/PLAY/TEARDOWN returned 200 and PCMU RTP was accepted. The speaker now tries the ONVIF media URL first and /h264_stream as fallback (api.get_rtsp_backchannel_endpoint, media_player._async_find_backchannel); the E2E check tries both paths. Unit suite 847 of 848 (same pre-existing jinja2 import error). This replaces the hypothesis in the description about which tracks fw 3.x offers. The profile token profile_h264_hq is hard-coded; other models and fw 2.x are not verified.
<!-- SECTION:NOTES:END -->
