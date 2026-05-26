# Runtime State Report

Generated: 2026-05-26 20:34 IDT

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

## Post-Window Recheck

- latest scheduler status: `not_due`
- recheck due: `false`
- transition decision: `WAIT_UNTIL_NEXT_SAFE_AT`
- next safe timestamp: `2026-05-27T11:19:56.313413+00:00`
- sends started: `false`
- live outreach allowed: `false`

## Verification

- API tests: `162 passed`
- smoke test: PASS
- Huanshu local adapter: PASS including admin transition panel
- secondary QA plugins: PASS or non-blocking warning, 0 blockers
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Wait until `2026-05-27T11:19:56.313413+00:00`, then let the post-window recheck agent execute no-send checks and transition only to warmup-ready if all gates pass.
