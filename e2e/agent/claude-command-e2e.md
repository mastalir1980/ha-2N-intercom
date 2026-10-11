---
description: Deploy the integration to staging HA, run the E2E suite against the real 2N intercom and triage failures into Backlog.md
argument-hint: "[--worktree | --ref <ref>] [--relays]"
---

Run the E2E pipeline for this repo: `bash e2e/run.sh --no-agent $ARGUMENTS`
(default when no arguments: `--worktree`, so uncommitted work is tested).

- Never pass `--relays` unless the user explicitly asked for relay tests in this conversation —
  it physically opens doors/gates.
- When it finishes, read `e2e/reports/latest/summary.json`.
- If it failed, follow `e2e/agent/triage.md` yourself (with `{{REPORT}}` = `e2e/reports/latest`):
  deduplicate against open bugs and create/update Backlog.md bug tasks via the `backlog` CLI.
- Report back: status, which tests failed, and the task ids you created or updated.
