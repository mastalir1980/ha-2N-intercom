#!/usr/bin/env bash
# Hermes cron script (copy to ~/.hermes/scripts/ha2n-e2e.sh on the Pi).
# Runs the read-only E2E check; prints a summary only when tests actually ran.
exec bash "$HOME/ha-2n-intercom/e2e/e2e.sh" hermes
