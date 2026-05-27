# Runtime State Report

Generated: 2026-05-27 04:31 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- current branch head before P59 commit: `584c938c796617cdd17dc0b5a0642065f5957919`
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
- mailer digest trend guard agent runs: `1`
- latest trend guard compact summary: `PASS_NO_SEND`
- latest trend guard raw history rows included: `false`
- protected admin surfaces compact trend guard summary: `true`
- daily loop includes trend guard agent: `true`
- mailer policy score: `100`
- mailer policy decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- mailer policy blockers: `0`
- mailer policy score agent runs: `1`
- protected admin surfaces policy score evidence: `true`
- daily loop includes policy score agent after trend guard: `true`
- mailer policy score history rows: `2`
- latest policy score history score: `100`
- latest policy score history decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- latest policy score history send state: `false`
- digest includes policy score history evidence: `true`
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

- targeted P59 policy history tests: `31 passed`
- API tests: `303 passed`
- smoke test: `303 passed, ok`
- Next production build: `PASS`
- Huanshu admin visual gate P59: `PASS`
- Playwright desktop/mobile + axe + pa11y P59: `PASS`
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Continue the autonomous build/audit/fix loop. Warmup remains scheduled, but this pass did not force sends and did not enable live outreach.
