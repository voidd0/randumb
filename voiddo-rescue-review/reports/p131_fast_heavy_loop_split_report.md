# P131 Fast/Heavy Loop Split Report

Generated: 2026-05-29

## Change

Added a separate heavy autonomous loop:

- `runtime_heavy_loop_plan()`
- `run_heavy_loop()`
- `POST /admin/heavy-loop/run`

The core daily loop now stays focused on safety, mail, queue hygiene, reporting, and status. Heavy sourcing/scanner/campaign/visual/self-development work can be run separately with bounded payloads.

## Reason

The core loop must remain responsive even when public lead discovery, scanner waits, or contact enrichment are slow. Splitting heavy work prevents the mail/canary safety loop from being blocked by sourcing work.

## Safety

- Heavy loop still uses existing no-send/gated agents.
- No outreach send flags are enabled by this change.
- No warmup is forced.
- Non-Rescue projects are untouched.

