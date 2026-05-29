# P133 Host Autonomy Runner Lane Split Report

Generated: 2026-05-29

## Change

Host runner `scripts/rescue_autonomous_loop.py` now supports:

- `--mode core`
- `--mode full`
- `--mode heavy`

Heavy mode calls the protected API endpoint:

- `POST /admin/heavy-loop/run`

The systemd heavy/full timer template now uses heavy mode with its own lock.

The fast core lane now also runs the canary recovery stack:

- `canary_bounce_recovery_agent`
- `outreach_queue_suppression_hygiene_agent`
- `outreach_transport_block_hygiene_agent`
- `canary_clean_window_forecast_agent`
- `canary_resume_plan_agent`
- `canary_next_batch_preparer_agent`

This keeps pause recovery, stale transport-block cleanup, clean-window forecasting, and next-batch preparation active without waiting for the heavier sourcing/visual/self-development lane.

## Safety Fix

`--allow-agent-failures` no longer bypasses live/send safety checks. It only suppresses service failure for agent failures; the runner still fails if the loop reports live outreach permission outside the approved canary scoreboard signal.

## Reason

The host full autonomous service had failed on agent failures. Splitting the heavy lane from the fast core lane lets mail/canary safety continue while heavier sourcing/scanner/self-development work is tracked separately.

## Safety

- No mail was sent by this change.
- No warmup was forced.
- No non-Rescue projects were touched.
