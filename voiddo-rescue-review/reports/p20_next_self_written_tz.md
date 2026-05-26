# P20 Self-Written TZ — Timer Integration For Post-Window No-Send Transition

Generated: 2026-05-26 20:34 IDT

## Goal

Wire the post-window no-send recheck into the existing Rescue automation cadence so it runs automatically after `next_safe_at`, then only updates readiness evidence without forcing sends.

## Tasks

1. Add script or worker entrypoint for post-window recheck scheduler.
2. Add systemd timer or integrate into existing Rescue-safe timer if appropriate.
3. Ensure timer action:
   - runs no-send checks only
   - never enables live outreach
   - never forces warmup outside natural due calendar
   - writes report/state
4. Add tests:
   - script invokes scheduler
   - not-due exits cleanly
   - due mocked clean transitions to warmup-ready evidence only
   - live outreach remains blocked
5. Run QA:
   - pytest
   - smoke
   - Huanshu
   - extra visual QA plugins

## Acceptance

- At least 166 tests pass.
- Timer/entrypoint is Rescue-only.
- Warmup sent remains `0` unless the existing natural warmup timer later passes all gates.
- Live outreach remains `0`.
- Non-Rescue projects untouched.
