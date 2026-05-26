# P19 Self-Written TZ — Post-Window Recheck Scheduler + Warmup-Ready Transition

Generated: 2026-05-26 20:21 IDT

## Goal

Make the system schedule and execute a no-send clean-window recheck after the current safe timestamp, then transition to a warmup-ready state only if all gates pass.

## Tasks

1. Add scheduled recheck metadata:
   - next_safe_at
   - recheck_due
   - recheck_executed_at
   - transition_decision
2. Add agent that runs only no-send checks after `next_safe_at`.
3. If clean:
   - rerun mail QA without deliverability send
   - rerun warmup pre-send gate
   - update dashboard state to `WARMUP_READY_PENDING_NATURAL_TIMER`
4. If not clean:
   - compute next safe timestamp again
   - write blocker report
5. Tests:
   - not due before next_safe_at
   - due after next_safe_at
   - transition ready when mocked clean
   - no live outreach unlock
   - no send forced
6. QA:
   - pytest
   - smoke
   - Huanshu
   - extra visual QA plugins

## Acceptance

- At least 160 tests pass.
- Live outreach remains `0`.
- Warmup is not manually forced.
- Reports stay honest and evidence-based.
- Non-Rescue projects untouched.
