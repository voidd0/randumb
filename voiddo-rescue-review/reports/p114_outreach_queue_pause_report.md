# P114 Outreach Queue Pause Report

Generated: 2026-05-29 14:00 IDT

## Change

The outreach worker now checks queue-level pause gates before selecting due queued messages.

If any of these are active, the worker does not lock, mutate, send, or mark queued outreach rows as blocked:

- `OUTREACH_DRY_RUN=true`
- `OUTREACH_PAUSED=true`
- `FIRST_LIVE_SEND_FLAG=false`
- `runtime_controls.pause_outreach=true`
- `runtime_controls.pause_workers=true`
- `runtime_controls.pause_all_workers=true`

If a pause appears after a row is already selected, the worker restores the row to `queued` with a delayed `send_after` instead of converting it to `transport_blocked`.

## Runtime Evidence

- Current queue pause reason: `runtime_pause_outreach`
- Manual worker queue call: `processed=0`, `sent=0`, `blocked=0`, `paused=true`
- Live outreach did not continue.

## Verification

- Worker focused tests: `6 passed`
- Worker rebuilt and healthy.
- Non-Rescue projects untouched.
