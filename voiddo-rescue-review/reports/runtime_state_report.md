# Runtime State Report

Generated: 2026-05-27 02:04 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- current branch head before P50 commit: `12b080b82a415caf0be3461d101bd72b606c6b15`
- checkout status: `READY`
- mail auth status: `PASS`
- latest mail QA decision: `PASS`
- approved test inbox count: `7`
- approved warmup recipient count: `7`
- scheduled warmup count: `28`
- warmup sent count: `0`
- live outreach sent count: `0`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Mailer Ops Retention

- retention history rows: `1`
- latest retention history: `0:1:0:send=false`
- protected history endpoint: `implemented`
- admin history surface: `implemented and visual QA passed`
- raw recipient addresses included: `false`
- secrets included: `false`

## Mailer Queue Hygiene

- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- send_mail: `false`
- live_outreach_allowed: `false`

## Verification

- API tests: `280 passed`
- smoke test: `280 passed, ok`
- visual QA: `PASS`
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Continue the autonomous build/audit/fix loop. Warmup remains scheduled, but this pass did not force sends and did not enable live outreach.
