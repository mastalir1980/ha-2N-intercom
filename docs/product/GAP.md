# GAP — what 2N + HA offer vs. what ha-2n-intercom does

Owner: Steve (product analyst). First version 2026-10-26, last updated 2026-10-31. Baseline: main @ d4bf6da (v1.5.1 + merged v1.6 work: TASK-39, TASK-2.3).
Roadmap context: docs/ROADMAP-NAVRH.md (2026-10-24). Items already planned there are marked with their task id.
Sources: see 2N-CAPABILITIES.md and HA-LANDSCAPE.md (every claim there has URL + date).

## A. Compliance gaps (HA changes with a deadline)

| # | Gap | Deadline | Size | Evidence | Note |
|---|---|---|---|---|---|
| A1 | Update listener (`__init__.py:586`, reloads on every entry update) **plus** explicit `async_reload` after `async_update_entry` in config flow (`config_flow.py:496`, `:644`, `:742`) | HA deprecation: listener + reloading methods in config flow → **error from 2026.12** | S | https://contributors.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/ (checked 2026-10-26); core PR diff https://github.com/home-assistant/core/pull/169198 (read 2026-10-27) | **Fact (2026-10-27):** the HA check sits only in `async_update_reload_and_abort` and in `_abort_if_unique_id_configured` when `updates` is passed. We call neither with updates (`config_flow.py:503`, `:798` without args) → HA will **not** flag us in 2026.12. **Remaining real issue (hypothesis, not verified on a device):** `async_update_entry` fires our update listener (reload) and we then call `async_reload` again → double reload / race in reauth, reconfigure, SSDP host change. Priority lowered: no deadline, quality fix. Proposed to Jan as an alternate on 2026-10-27. |
| A2 | `DeviceInfo` dict-style writes `info["…"] = …` (`coordinator.py:1744-1753`) | 2026.11 compat layer, removal "later" (no date) | S | https://contributors.home-assistant.io/blog/2026/10/13/device-info-class/ (checked 2026-10-26) | Pass all fields in the constructor instead; works on old and new HA. Check `tests/_stubs.py`. |
| A3 | No `async_entity_id_changed` on entities with `async_added_to_hass` (`event.py:48`, `update.py:88`, + cover/switch) | compat removed **2027.11** | S | https://contributors.home-assistant.io/blog/2026/10/12/new-entity-lifecycle-hooks/ (checked 2026-10-26) | Only matters when user renames entity_id; not urgent. Needs min HA 2026.11 or a guarded implementation. |
| A4 | `manifest.json` has no `categories` | none; HACS action warns now, fails on unknown value | S | https://contributors.home-assistant.io/blog/2026/10/20/integration-categories/ (checked 2026-10-26) | Pick the right category from the official list (not read yet). Helps Marketplace discovery. |
| A5 | `manifest.json` `documentation` / `issue_tracker` point to fork `savek-cc` | — | S | ROADMAP-NAVRH.md §2.4 | With Marketplace (HA 2026.11) these links are shown to more users. Jan decides. |

Fine already (no gap): `step_id` everywhere (deadline 2027.5), no `DeviceEntry.config_entries`, no `RestoreStateData.last_states`,
doorbell event type `ring` matches HA standard `DoorbellEventType.RING`, own `brand/` folder present.

## B. Feature gaps (value for users)

| # | Gap | 2N capability | HA capability | Size | Status |
|---|---|---|---|---|---|
| B1 | **Two-way audio** in HA camera (talk to visitor from dashboard) | RTSP stream with audio (backchannel support **unknown**) | NEW in 2026.11: `CameraEntityCapabilities(two_way_audio=True)`, only over WebRTC (native or go2rtc), Labs preview, HTTPS only — https://contributors.home-assistant.io/blog/2026/10/24/camera-two-way-audio/ (checked 2026-10-26) | L (spike first) | Roadmap C3 "obousměrné audio (nejdřív spike)". **New fact:** HA now has the platform piece. Unknown: does 2N RTSP accept an audio backchannel (ONVIF backchannel / RTSP ANNOUNCE)? Must find in 2N docs, then the tester agent can check it on the E2E intercom. |
| B2 | Block access (away / night mode: cards and PINs stop working) | `POST /api/accesspoint/blocking/ctrl` + `blocking/status` (manual 3.3) | `switch` | S–M | Not in roadmap. New idea. |
| B3 | Ring indoor units from HA (e.g. second doorbell button, automation) | `POST /api/io/doorbell` (manual 3.3) | `button` | S | Not in roadmap. Niche. |
| B4 | Access / security events in automations | log events | event entity, event bus | M | Planned: TASK-6, TASK-5, TASK-7 (v1.6.0). Competitors (Hikvision core, UniFi Protect) added event entities in 2026.10 → confirms direction. |
| B5 | Firmware install from HA | `/api/firmware` + `apply` | update entity install | M | Planned: TASK-66 → TASK-65 (on-hold). New 2026.11 `has_update` override is a small nicety, not a blocker. |
| B6 | Cleaner options flow (hide fields that don't apply) | — | NEW 2026.11 `visible` condition on fields — https://contributors.home-assistant.io/blog/2026/10/21/form-fields-visible/ (checked 2026-10-26) | S–M | Needs `hacs.json` min HA 2026.11. Later, when we raise the minimum. Same feature works in the doorbell blueprint. |
| B7 | Restart button, config backup | `system/restart` (GET/POST, no params, System – Control; checked 2026-10-30 https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-1-api-system/5-1-3-api-system-restart), `api/config` | `button` (`ButtonDeviceClass.RESTART` in HA 2026.4.0) | S | Planned: roadmap D2, D3 (v1.7+). Restart proposed 2026-10-30. |
| B9 | Door state (`DoorStateChanged` opened/closed, door contact on an input configured under Hardware → Door) | log event, no privilege — https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-10-api-log/5-10-4-api-log-pull (checked 2026-10-30) | `binary_sensor` device_class `door` | S–M | Roadmap A5. Not subscribed today (`coordinator.py:126-136`). Open: initial state after HA start (no status endpoint known). Proposed 2026-10-30. |
| B10 | Ring event says which call button was pressed | `CallSessionStateChanged` `info` (button number), `KeyPressed` `%1`–`%150` (manual, checked 2026-10-30) | event attribute | S | DRAFT-1 / doc-1. Code drops `info`; KeyPressed regex accepts only `%1`–`%54` (`coordinator.py:211`) while the manual says `%1`–`%150`. Proposed 2026-10-30. |
| B8 | Call status control (issue #12: user wants to change/hang up call when door opens) | `call/hangup` | service exists (`hangup_call`) | S (docs) | **Hypothesis:** already solvable with existing `2n_intercom.hangup_call` + door sensor automation; answer in issue/README example. |

## C. Open questions

- TASK-73: does `/api/camera/caps` on an audio-only unit (IP Uni) answer code 1? #105 only shows code 1 for
  `/api/camera/snapshot`. Not verified; the E2E intercom has a camera, so the tester agent cannot check it. (2026-10-28)
- TASK-73: does an account without Camera Monitoring get code 10 from `camera/caps`? (hypothesis from the manual, 2026-10-28)

- Where are current 2N OS firmware release notes published? (wiki URL 404 on 2026-10-26)
- Does any 2N model support audio backchannel over RTSP/WebRTC? (needed for B1)
  **Partial answer (2026-10-29):** the 2N configuration manual (Streaming, latest) says the intercoms "fully implement
  ONVIF Profile T and Profile S" and that the 4-stream RTSP limit "includes ... audio return channel directed to the
  intercom" → the RTSP server does accept an audio return channel (fact from docs). Not verified: that go2rtc (HA's
  WebRTC provider) negotiates it with 2N, and whether the intercom plays that audio outside a call (hypothesis).
  https://wiki.2n.com/hip/conf/latest/en/5-konfigurace-interkomu/5-4-sluzby/5-4-2-streamovani
  HA side: `CameraEntityCapabilities` is in tag 2026.11.0b0 (`camera/entity.py:53`), core PR #184716 merged 2026-10-22.
  Community: PR #113 (vemboy200) updates the README limitation and offers to implement it.
- Right `categories` value for an intercom (A4). **Answered 2026-10-29:** core uses `security_safety.doorbells_intercoms`
  (doorbird), with `security_safety.cameras` too for axis/reolink/ring/unifiprotect (manifests at tag 2026.11.0b0).
- Access blocking (B2): does `accesspoint/blocking` also stop remote relay opens / exit button? Manual §5.17 does not say (2026-10-29).
