# Runtime State Report

Generated: 2026-05-26 19:55 IDT

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

## Customer And Monitoring

- customer journey snapshots: implemented
- customer access token table: implemented
- token dashboard API: implemented and sanitized
- token dashboard web route: implemented at `/customer/dashboard/[token]`
- monitoring targets: implemented
- monitoring runs: implemented
- monitoring due scheduler: implemented and kill-switch/scanner-pause gated
- monitoring failure handling: system event + review task

## Verification

- API tests: `144 passed`
- smoke test: PASS
- Huanshu local adapter: PASS including token dashboard and admin-auth screenshots
- secondary QA plugins: PASS or non-blocking warning, 0 blockers
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Wait until the recent bounce/DSN and SMTP rate-limit window clears, then rerun clean-window recovery and mail QA before any warmup send.
