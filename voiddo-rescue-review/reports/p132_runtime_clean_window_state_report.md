# P132 Runtime Clean Window State Report

Generated: 2026-05-29

## Change

Runtime state snapshots and `runtime_state_report.md` now include canary clean-window evidence:

- `canary_clean_window_status`
- `canary_clean_window_eligible_after`
- `canary_clean_window_seconds_remaining`
- split canary outreach counters for sent, bounced, sent-or-bounced, and queued.

## Reason

Runtime reports previously said only to wait for recent mail risk signals to clear. The autonomous system now records the exact clean-window eligibility time so owner-facing daily reports and admin state can explain when the next resume recheck is expected.

## Safety

- Read-only snapshot/report change.
- No mail was sent.
- No pause was cleared.
- No non-Rescue projects were touched.

