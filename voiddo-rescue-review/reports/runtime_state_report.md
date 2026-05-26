# Runtime State Report

Generated: 2026-05-26 19:25 IDT

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
- spam signal count, last 24h: `0`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Autonomous Mailer

- latest mailer status: `blocked_recent_mail_signals`
- next safe action: `wait_until_recent_signal_window_clears`
- clean-window recovery: `blocked_recent_signals`
- recovery sends started: `false`
- signal learning: active

## Customer Journey

- customer journey snapshots table: present
- paid fix request to Codex task linking: implemented
- protected customer journey endpoint: implemented
- customer-facing token access: not yet implemented, assigned to P15

## Verification

- API tests: `132 passed`
- smoke test: PASS
- Huanshu local adapter: PASS
- secondary QA plugins: PASS or non-blocking warning
- API/web/worker/postgres/redis: healthy

