# Runtime State Report

Generated: 2026-05-27 02:16 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- current branch head before P51 commit: `5ecdc8254d2addf5c488db392ae32dc33ad6ca69`
- checkout status: `READY`
- mail auth status: `PASS`
- latest mail QA decision: `PASS`
- approved test inbox count: `7`
- approved warmup recipient count: `7`
- scheduled warmup count: `28`
- warmup sent count: `0`
- live outreach sent count: `0`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Mailer Daily Evidence

- mailer ops retention history rows: `1`
- latest retention history: `0:1:0:send=false`
- mailer digest history rows: `1`
- latest digest history: `0:0:email=false`
- daily loop surfaces retention history evidence: `true`
- owner report includes retention history evidence: `true`
- raw recipient addresses included: `false`
- secrets included: `false`

## Mailer Queue Hygiene

- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- send_mail: `false`
- live_outreach_allowed: `false`

## Verification

- API tests: `282 passed`
- smoke test: `282 passed, ok`
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Continue the autonomous build/audit/fix loop. Warmup remains scheduled, but this pass did not force sends and did not enable live outreach.
