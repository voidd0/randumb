# Runtime State Report

Generated: 2026-05-27 01:47 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- current branch head before P49 commit: `f78d5b7b438765c0858f1d8467788dfd119137a1`
- checkout status: `READY`
- mail auth status: `PASS`
- latest mail QA decision: `PASS`
- approved test inbox count: `7`
- approved warmup recipient count: `7`
- scheduled warmup count: `28`
- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- bounce/DSN count, last 24h: `0`
- SMTP rate-limit signal count, last 24h: `0`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Mailer Ops Retention

- retention history rows: `1`
- latest retention history: `0:1:0:send=false`
- mailer ops rows: `1`
- mailer ops synthetic rows: `0`
- latest mailer ops action: `digest_history_cleanup:completed:send=false`
- mailer ops retention agent runs: `1`
- latest mailer ops retention agent: `completed:0:1:send=false`

## Mailer Queue Hygiene

- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- raw recipient addresses included: `false`
- send_mail: `false`
- live_outreach_allowed: `false`

## Verification

- API tests: `278 passed`
- smoke test: `PASS (278 passed, ok)`
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Continue the self-written build/audit/fix loop. Warmup remains scheduled, but this pass did not force sends and did not enable live outreach.
