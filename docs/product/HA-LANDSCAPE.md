# Home Assistant landscape for ha-2n-intercom

Owner: Steve (product analyst). First version 2026-10-26, last updated 2026-10-31. Integration baseline: v1.5.1, `hacs.json` `homeassistant: 2026.4.0`.
"Impact" lines are my analysis against main @ d4bf6da (fact = grep result, hypothesis = marked).

## 1. Deprecations and deadlines that touch us

| Change | HA version | Deadline | Impact on us | Source (checked 2026-10-26) |
|---|---|---|---|---|
| `DeviceInfo` becomes a dataclass; `[]`, `.get()`, `.update()` kept as compat layer "deprecated and removed in a later version"; unset field reads `UNDEFINED` | 2026.11 | not set yet | **Fact:** `coordinator.py:1744-1753` writes `info["configuration_url"]`, `info["serial_number"]`, `info["hw_version"]`, `info["connections"]` → should move to attributes. Also `tests/_stubs.py` stub may need update. | https://contributors.home-assistant.io/blog/2026/10/13/device-info-class/ |
| Entities implementing `async_added_to_hass` / `async_will_remove_from_hass` must implement `async_entity_id_changed` to get in-place entity_id rename; otherwise removed + re-added | 2026.11 | compat removed **2027.11** | **Fact:** `event.py:48` and `update.py:88` implement `async_added_to_hass`; `cover.py`, `switch.py` mention the hooks too. No `async_entity_id_changed` anywhere. | https://contributors.home-assistant.io/blog/2026/10/12/new-entity-lifecycle-hooks/ |
| `step_id` required in `async_show_form/menu/progress/external_step` | warning now | **2027.5.0** | **Fact:** all 7 `async_show_form` calls in `config_flow.py` pass `step_id`. No action. | https://contributors.home-assistant.io/blog/2026/10/23/flow-results-require-step-id/ |
| `DeviceEntry.config_entries` / `primary_config_entry` warn for custom integrations | 2026.10 | **2027.10** | **Fact:** not used. No action. | https://contributors.home-assistant.io/blog/2026/09/15/device-entry-config-entries-deprecation/ |
| Config entry listener + reloading methods in a config flow (fixes: drop listener, or `async_update_and_abort()`, or `reload_on_update=False`) | 2026.6 | error from **2026.12** | **Fact:** `__init__.py:586` registers an update listener that reloads; `config_flow.py:496/644/742` call `async_reload` after `async_update_entry`. **Hypothesis:** the core check targets the helper methods, which we don't use — verify against core PR #169198. See GAP A1. | https://contributors.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/ |
| Camera two-way audio: `CameraEntityCapabilities(two_way_audio=True)`; frontend gets it only over WebRTC (native or go2rtc), Labs preview, HTTPS | 2026.11 | — (new feature) | We use `MjpegCamera` + RTSP `stream_source`; no WebRTC. See GAP B1. | https://contributors.home-assistant.io/blog/2026/10/24/camera-two-way-audio/ |
| Doorbell event entities must include `DoorbellEventType.RING` | 2026.5-ish (post 2026-04-15) | — | **Fact:** `event.py:35` `_attr_event_types = ["ring"]`. OK. | https://contributors.home-assistant.io/blog/2026/04/15/doorbell-standard-event-type/ |
| `RestoreStateData.last_states` removed, restore indexed by registry ID | 2026.11 | — | **Fact:** not used. | https://contributors.home-assistant.io/blog/2026/10/06/restore-state-last-states-removal/ |

## 2. HACS → Marketplace (big)

- **Fact:** From HA **2026.11** HACS ships inside HA as the **Marketplace** (Settings > Marketplace). Same catalog
  (hacs/default) and same `hacs.json`. Existing HACS installs carry over with their update entities. HACS custom
  integration can't be installed on 2026.11+.
  Source: https://www.hacs.xyz/docs/marketplace/ (checked 2026-10-26)
- **Fact:** Marketplace install checks: `hacs.json` in root, domain chars, unique domain, `manifest.json` must have a loadable
  `version`, minimum HA version from `hacs.json` (older releases offered instead).
  Source: https://contributors.home-assistant.io/marketplace/reference/validation/ (checked 2026-10-26)
- **Fact:** Releases reach users via catalog (every 4 h) → Marketplace (every 6 h); repos added by link update every 48 h via
  GitHub API. Release body = notes shown in the update entity; put user actions at the top.
  Source: https://contributors.home-assistant.io/marketplace/guides/releases/ (checked 2026-10-26)
- **Fact:** New optional manifest key `categories` (1–3, e.g. `"energy.ev_charging"`). Hassfest only warns on unknown;
  **the HACS action warns when missing and fails on an unknown category**. Marketplace will browse by category.
  Source: https://contributors.home-assistant.io/blog/2026/10/20/integration-categories/ (checked 2026-10-26)
  Impact: our `manifest.json` has no `categories`; `.github/workflows/hacs.yml` uses `hacs/action@main` → expect a warning.
  The right category value (security/intercom?) is **unknown** — must read the official category list before proposing.
- Brands: custom integrations can ship their own brand images since 2026.3; HACS action check `brands` accepts a `brand/`
  folder with `icon.png`. **Fact:** we ship `custom_components/2n_intercom/brand/`.
  Source: https://contributors.home-assistant.io/blog/2026/02/24/brands-proxy-api/ (title seen in blog index), validation page above.

## 3. New capabilities we could use

| Feature | HA version | Possible use | Source (checked 2026-10-26) |
|---|---|---|---|
| `visible` condition on flow fields (show field only when another field has a value) | 2026.11 | Options flow: show camera fields only when camera enabled, insecure toggle only for Basic/HTTP, etc. Needs min HA 2026.11 in `hacs.json`. Also works in blueprint inputs → doorbell blueprint. | https://contributors.home-assistant.io/blog/2026/10/21/form-fields-visible/ |
| `UpdateEntity.has_update` override | 2026.11 | Firmware entity could say "update available" straight from the 2N server's type matching instead of the installed=latest trick (`update.py:141`). Low value. | https://contributors.home-assistant.io/blog/2026/10/10/update-entity-update-availability/ |
| Child devices (composition, not via_device) | 2026.9 | Hypothesis: extension modules (I/O, card reader) could be child devices. Low value now. | https://contributors.home-assistant.io/blog/2026/10/22/child-devices/ |
| Config entry exceptions in `async_migrate_entry` | — | Translatable migration errors. | https://contributors.home-assistant.io/blog/2026/09/17/Use-config-entry-exc-in-migration/ |
| Shared abort reasons translated centrally | 2026.10 | Could drop own translations for common aborts (e.g. `already_configured`). | https://contributors.home-assistant.io/blog/2026/09/28/central-config-flow-abort-reasons/ |
| Config entry functions return `None` (core only; custom may keep bool, no deprecation). `return False` → generic translated `ConfigEntryError`. New helper `async_unload_platforms_or_raise`. | 2026.11 | **Fact:** we return bool (`__init__.py:587` `return True`, unload returns `unload_ok` from `async_unload_platforms`, `__init__.py:610`). Not affected. Optional polish: raise own translated exceptions. | https://contributors.home-assistant.io/blog/2026/10/23/config-entry-methods-return-none/ (checked 2026-10-27) |
| Debug console (Python in running HA) | — | Dev/test aid only. | https://contributors.home-assistant.io/blog/2026/10/17/debug-console/ |

## 4. Release 2026.10 (user side)

- Trigger IDs get a UI ("Triggered by" condition). Our blueprints/README examples using trigger IDs keep working (YAML unchanged).
  Source: https://www.home-assistant.io/blog/2026/10/07/release-202610/ (checked 2026-10-26)
- Competitors: **Hikvision** core integration added event entities that tell what triggered (doorbell etc.); **UniFi Protect** key fob event entity.
  Same source. Confirms "event entity per doorbell/access" is the HA norm — matches our v1.6 TASK-5/6/7 direction.
- **Hypothesis (forum reports, not confirmed by HA):** camera streaming regressions after 2026.10.0 (choppy streams, UniFi Protect
  streams failing; PyAV 17→19 mentioned). Relevant if 2N users report stream issues on 2026.10.
  Source: comments on https://community.home-assistant.io/t/2026-10-you-are-here/1027779 (checked 2026-10-26)
- No backward-incompatible change in 2026.10 that affects us (list read). Same source, section "Backward-incompatible changes".

## 5. Not checked yet / gaps in this file

- Community forum search for 2N threads: rate-limited on 2026-10-26; redone 2026-10-27 (one search, "2N intercom", latest):
  no new 2N thread. Recent related threads are other brands (Aiphone, LIXIL, Hikvision ISAPI bridge, ESP32 doorbell).
  Source: https://community.home-assistant.io/search?q=2N%20intercom%20order%3Alatest (checked 2026-10-27)
- Integration quality scale rule changes in 2026.10/11: not found in blog index; to check the rules page next run.
- 2026.11 beta release notes (due early November).
