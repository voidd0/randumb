# P126 Bounce Recovery Metric Semantics Report

Generated: 2026-05-29

## Change

`canary_bounce_recovery` now separates:

- `blocked_outreach_row_count`: active failed/blocked/transport-blocked rows.
- `bounced_outreach_row_count`: rows marked bounced after DSN handling.

Bounced outreach rows remain mail-risk evidence, but they no longer trigger the active queue blocker `blocked_outreach_rows_present`.

## Reason

The canary pipeline now treats bounced rows as:

- evidence that a canary attempt happened.
- a clean-window blocker while bounce/DSN signals are recent.
- not a permanent active queue blocker after the recovery and clean-window process completes.

## Verification

Added regression coverage to confirm a bounced outreach row does not count as an active blocked row.

## Safety

- No mail was sent.
- No runtime pause was cleared.
- No raw recipient addresses or secrets are included.
- Non-Rescue projects were not touched.

