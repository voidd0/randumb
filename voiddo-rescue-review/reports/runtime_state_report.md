# Runtime State Report

Generated: 2026-05-27 04:07 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- current branch head before P58 commit: `5599bfa8262bac89b30da20d6ef85529084f2644`
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

- targeted P58 mailer policy/admin tests: `45 passed`
- API tests: `299 passed`
- smoke test: `299 passed, ok`
- Next production build: `PASS`
- Huanshu admin visual gate P58: `PASS`
- Playwright desktop/mobile + axe + pa11y P58: `PASS`
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Continue the autonomous build/audit/fix loop. Warmup remains scheduled, but this pass did not force sends and did not enable live outreach.
