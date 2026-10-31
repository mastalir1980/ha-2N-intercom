# Product analysis

Kept by Steve, the product analyst agent. They are the input for grooming:
they help pick the next tasks and get them ready for the coder.

| File | What it contains |
|---|---|
| [`2N-CAPABILITIES.md`](2N-CAPABILITIES.md) | What 2N intercoms can do according to public 2N sources: HTTP API endpoints (used and not used yet), error codes, log events, firmware/support policy, product news. |
| [`HA-LANDSCAPE.md`](HA-LANDSCAPE.md) | Home Assistant changes that affect this integration: deprecations with deadlines, HACS → Marketplace, new platform features we could use, release notes. |
| [`GAP.md`](GAP.md) | The difference between what 2N + HA offer and what the integration does today: compliance gaps (A), feature gaps (B), open questions (C). Planned items link to their Backlog task. |

## Rules for these files

- Every claim has a source URL and the date it was checked.
- **Fact** = seen in a source, in the code or in an API response. **Hypothesis** = our reading, marked as such.
- Code pointers (`file.py:line`) refer to the commit named in each file's header; lines may move later.
- Public sources only. No details about the E2E environment (hosts, IPs, device model, firmware build) and no secrets.
- These files do not decide what gets built. Jan does; approved work becomes a Backlog task.
