# Warmup Calendar Health Report

Generated: 2026-05-26 18:58 IDT

## State

- scheduled total: `28`
- warmup sent today: `0`
- warmup sent total: `0`
- live outreach sent total: `0`
- latest mail QA decision: `PASS`
- recent bounce/DSN count, last 24h: `2`
- recent SMTP rate-limit count, last 24h: `1`
- recent spam signal count, last 24h: `0`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## P12 Schedule Gate

- provider-spacing apply status: `blocked_safety_gate`
- reason: recent mail signals
- schedule changed: `false`
- sends started: `false`

## Next Allowed Action

No warmup send should be attempted until the recent bounce/DSN and rate-limit window clears and mail QA is rechecked. The existing systemd warmup timer remains safe because every due send is pre-gated.

