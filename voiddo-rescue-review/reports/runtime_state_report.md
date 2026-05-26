# Runtime State Report

Generated: 2026-05-26 18:58 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- latest synced review HEAD before P12 export: `778971a8d01f54574cf57f6cd5540d0c8462fcc7`
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

## Current Safe Action

Wait until the recent bounce/DSN and SMTP rate-limit window clears, then rerun mail QA and provider-spacing apply gate. No cold outreach is allowed.

## Service Health

- `voiddo_rescue_api`: healthy
- `voiddo_rescue_web`: healthy
- `voiddo_rescue_worker`: healthy
- `voiddo_rescue_postgres`: healthy
- `voiddo_rescue_redis`: healthy

## P12 Agent State

- `warmup_spacing_apply_gate_agent`: completed
- apply decision: `blocked_safety_gate`
- reason: recent mail signals
- schedule applied: `false`
- sends started by apply gate: `false`
- daily loop agents executed: `16`
- self-audit status: `needs_fix`
- self-audit score: `60`

## Visual And Design QA

- Huanshu local adapter: PASS on public routes and authenticated admin
- `axe-core-playwright`: PASS
- `pa11y`: PASS
- `pixelmatch`: PASS
- `lighthouse-ci`: PASS_WITH_WARNINGS, no blocker

## Verification

- API tests: `118 passed`
- smoke test: PASS
- public health endpoints: PASS
- admin auth route checked with bearer token

