# Runtime State Report

Generated: 2026-05-27 02:49 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- current branch head before P52 commit: `4a0efb0b52f02ccda2c920d04087c35bb8c411ee`
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
- daily digest admin surfaces ops retention history rows: `true`
- daily digest admin surfaces ops retention no-send state: `true`
- daily digest admin surfaces ops retention privacy/secrets flags: `true`
- mailer digest trend guard decision: `PASS_NO_SEND`
- mailer digest trend guard regressions: `0`
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

- targeted P53 digest/admin/trend tests: `39 passed`
- API tests: `287 passed`
- smoke test: `287 passed, ok`
- Next production build: `PASS`
- Huanshu admin visual gate: `PASS`
- Playwright desktop/mobile + axe + pa11y: `PASS`
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Continue the autonomous build/audit/fix loop. Warmup remains scheduled, but this pass did not force sends and did not enable live outreach.
