# Runtime State Report

Generated: 2026-05-26 20:09 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- checkout status: `READY`
- mail auth status: `PASS`
- latest mail QA decision: `PASS`
- approved test inbox count: `7`
- approved warmup recipient count: `7`
- scheduled warmup count: `28`
- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- bounce/DSN count, last 24h: `2`
- SMTP rate-limit signal count, last 24h: `1`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Customer, Monitoring, And Mailer Autonomy

- customer token dashboard web route: implemented and sanitized
- monitoring due scheduler: implemented and kill-switch/scanner-pause gated
- monitoring summary endpoint: implemented
- mailer control-room endpoint: implemented
- owner status report endpoint: implemented, file-only under current mail blockers
- admin dashboard: shows mailer signals, lessons, clean-window recovery, monitoring evidence, and warmup calendar evidence

## Verification

- API tests: `150 passed`
- smoke test: PASS
- Huanshu local adapter: PASS including admin control room
- secondary QA plugins: PASS or non-blocking warning, 0 blockers
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Wait until the recent bounce/DSN and SMTP rate-limit window clears, then rerun clean-window recovery and mail QA before any warmup send.
