# P122 Runtime Canary Metric Consistency Report

Generated: 2026-05-29T14:49:07+03:00

## Objective

Make live canary metrics explicit after a sent outreach row is later marked `bounced`, so runtime reports do not confuse accepted sends with total canary volume.

## Changes

- `runtime_state_snapshot()` now reports:
  - `live_outreach_sent_count`
  - `live_outreach_bounced_count`
  - `live_outreach_sent_or_bounced_count`
  - `live_outreach_queued_count`
- Mailer business KPI now exposes the same split.
- Active-canary next-action logic uses `sent_or_bounced` for volume evidence while bounce signals remain separate blockers.

## Runtime Result

- Sent: `11`
- Bounced: `1`
- Sent-or-bounced canary volume: `12`
- Queued: `7`
- Next action: wait for recent mail risk signal window to clear, then recheck mail QA.

## Verification

- Runtime/KPI focused suite: `43 passed`.
- Runtime snapshot and KPI now agree on sent/bounced/sent-or-bounced counts.
- Rescue services healthy.
