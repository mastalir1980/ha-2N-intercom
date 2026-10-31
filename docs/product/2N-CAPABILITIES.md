# 2N capabilities (public sources)

Owner: Steve (product analyst). First version 2026-10-26, last updated 2026-10-31.
Rule: every claim has a source URL and the date it was checked. "Fact" = seen in the source; "Hypothesis" = my reading.

## 1. HTTP API manual

- Current manual versions offered on the wiki: **3.3** (latest) and **2.50_LTS**. PDF: `2N_IP_HTTP_API_manual_EN_3.3.pdf`.
  Source: https://wiki.2n.com/hip/hapi/latest/en (checked 2026-10-26)
- Service groups in manual 3.3 (section 5): system (info, status, restart, caps, time, timezone), firmware (upload, apply, reject),
  config (backup/restore, factoryreset, holidays), switch, io (caps, status, ctrl, **doorbell**), phone (status, calllog, config),
  call (status, dial, answer, hangup), camera (caps, snapshot), display (caps, image, language, text), log (caps, subscribe,
  unsubscribe, pull), audio test, email send, pcap, dir (template, create, update, delete, get, query), mobilekey,
  lpr (licenseplate, image), accesspoint (blocking ctrl/status, grantaccess), lift grantaccess, automation trigger,
  cert (ca, user, csr).
  Source: https://wiki.2n.com/hip/hapi/latest/en (table of contents, checked 2026-10-26)

### Endpoints the integration uses today (fact, `api.py` on main @ d4bf6da)

`accesspoint/grantaccess`, `call/answer|hangup|status`, `camera/caps|snapshot`, `dir/query`, `io/caps|ctrl|status`,
`log/caps|pull|subscribe|unsubscribe`, `phone/status`, `switch/caps|ctrl|status`, `system/caps|info`.
Firmware availability uses the public update server (`const.py:72`), not `/api/firmware`.

### Endpoints not used yet, with possible value

| Endpoint | What it does (per manual) | Privilege | Possible HA use | Source (checked 2026-10-26) |
|---|---|---|---|---|
| `POST /api/io/doorbell` | Triggers the logical doorbell in answering units; no params, returns `{"success": true}` | Entries and Exits – Control | `button` "Ring indoor units" (e.g. from a second doorbell or automation) | https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-5-api-io/5-5-4-api-io-doorbell |
| `POST /api/accesspoint/blocking/ctrl?id=0|1&action=on|off` + `blocking/status` | Blocks access on entry (0) / exit (1) access point; error 18 = access point disabled | Access Control (service group API Access Control) | `switch` "Entry blocked" (away/night mode: cards/PINs stop working) | https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-17-api-accesspoint/5-17-1-api-accesspoint-blocking-ctrl |
| `GET/POST /api/automation/trigger?triggerId=<name>` | Fires an HttpTrigger block in 2N Automation; error 12 "HttpTrigger not found" | Access to Automation | Service `trigger_automation` (needs Automation licence — ROADMAP lists "licensed Automation API" as out of scope) | https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-19-api-automation/5-19-1-api-automation-trigger |
| `api/system/restart` | Restart device | System – Control | `button` restart (roadmap D2) | https://wiki.2n.com/hip/hapi/latest/en (TOC) |
| `api/config` | Config backup/restore | System – Control | Backup (roadmap D3) | https://wiki.2n.com/hip/hapi/latest/en (TOC) |
| `api/call/dial` | Outgoing call | Phone/Call | Service "call peer" | https://wiki.2n.com/hip/hapi/latest/en (TOC) |
| `api/display/*` | Display text/image | — (not checked) | `notify`/`text` to intercom display (only display models) | https://wiki.2n.com/hip/hapi/latest/en (TOC) |
| `api/lpr/*` | Licence plate recognition | — (not checked) | Event with plate (niche, needs LPR camera) | https://wiki.2n.com/hip/hapi/latest/en (TOC) |
| `api/cert/*` | Upload CA / user cert, CSR | — (not checked) | Hypothesis: could help DRAFT-2 (TOFU pin) or a "install trusted cert" flow | https://wiki.2n.com/hip/hapi/latest/en (TOC) |

### Error codes (fact, manual 3.3 §2.3, checked 2026-10-28)

Source: https://wiki.2n.com/hip/hapi/latest/en/2-popis-protokolu-http-api/2-3-odpovedi-na-pozadavky
Negative reply `{"success": false, "error": {"code", "description", "param"}}`, with HTTP 200 or 401.
- 1 function is not supported: "The requested function is unavailable in this model."
- 2 invalid request path · 3 invalid request method
- 4 function is disabled: the service is off in Services / HTTP API
- 7 invalid connection type: HTTPS required
- 8 invalid authentication method (Basic sent where only Digest is enabled)
- 9 authorisation required (with HTTP 401) · 10 insufficient user privileges
- 11 missing mandatory parameter · 12 invalid parameter value · 13 parameter data too big
- 14 unspecified processing error · 15 no data available · 17 parameter collision
- 18 request is rejected · 19 file version lower than minimum

Relevant to TASK-73 / TASK-12:
- `GET /api/camera/caps` belongs to the **Camera** service and needs the **Camera Monitoring** privilege; it returns
  `jpegResolution` + `sources`. Source: https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-8-api-camera/5-8-1-api-camera-caps (checked 2026-10-28)
  → Hypothesis: on an account without Camera Monitoring the device answers code 10, not code 1. So code 10 must never
  be read as "no camera".
- `GET /api/system/caps` (System privilege) lists `options` incl. `"camera": "active"`, `"video"`, `"motionDetection"`.
  Source: https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-1-api-system/5-1-4-api-system-caps (checked 2026-10-28)
  Fact from #105: on the IP Uni this call answered code 10 (account offers only Phone/Calls + Keypad), so it is not a
  reliable "no camera" signal on its own.

### Security log events (fact, manual 3.3 §5.10.4 `api/log/pull`, checked 2026-10-28)

Source: https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-10-api-log/5-10-4-api-log-pull
- `TamperSwitchActivated` `{state: in|out}` (needs Digital Inputs | Tamper Switch configured)
- `UnauthorizedDoorOpen` `{state: in|out}` and `DoorOpenTooLong` `{state: in|out}` (need a door-open switch on an input,
  Digital Inputs | Door State)
- `SilentAlarm` `{ap, session, name, uuid}` (momentary; `name` = directory user)
- `LoginBlocked` `{address}` = IP address that repeatedly entered wrong web login → privacy-relevant
- `AccessLimited` `{ap, type, state}`: 5 failed authentications, access module blocked for 30 s
- `ApiAccessRequested` is logged "whenever a request was sent to /api/accesspoint/grantaccess with the result
  success: true", params `ap, valid, session, uuid`. Source: …/5-10-api-log/5-10-1-api-log-caps (checked 2026-10-28)

## 2. Firmware and support policy

- 2N commits to security updates and **LTS firmware for at least 5 years after end of sale**; 2N is a **CVE Numbering
  Authority since November 2025**, 12 CVEs published since joining the CVE program in 2024.
  Source: https://www.2n.com/en-GB/newsroom/5-ways-2n-helps-you-manage-cybersecurity-risks/ (published 2026-10-26, checked 2026-10-26)
- Firmware release notes on the wiki: the URL I tried (`wiki.2n.com/hip/rn/latest/en`) returns 404. **Unsure** where the current
  2N OS release notes live; to find next run. (checked 2026-10-26)

## 3. Products and ecosystem news

- 2N IP Force 2.0 is promoted as "new product" on the newsroom (article from 2025-08-04).
  Source: https://www.2n.com/en-GB/news/ (checked 2026-10-26). Product page blocked by a bot wall (HTTP 403) from here.
- My2N App: new unified dashboard, enabled for everyone (cloud — out of scope for us).
  Source: https://www.2n.com/en-GB/newsroom/my2n-app-gets-a-new-unified-dashboard/ (2026-10-15, checked 2026-10-26)
- KONE lift integration extended to 2N Indoor View (out of scope: lift control).
  Source: https://www.2n.com/en-GB/newsroom/expanding-the-kone-integration-to-2n-indoor-view/ (2026-10-19, checked 2026-10-26)
- No discontinued product announcement found in the newsroom since 2026-09-21. (checked 2026-10-26)
