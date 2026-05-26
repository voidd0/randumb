# Warmup Readiness Report

Updated: 2026-05-26 13:55 IDT

## Status

Warmup is implemented but blocked. It has not started.

Current blockers:

- Owner-approved warmup recipient pool exists.
- Owner-approved deliverability test inbox pool exists.
- Latest mail QA decision is `FAIL_BLOCK_LAUNCH` because deliverability diagnostics hit rate-limit and bounce/DSN was observed.

## Implemented

- `WARMUP_RECIPIENT_POOL` runtime config support.
- Protected import endpoint: `POST /warmup/recipients/import`.
- Import validation rejects invalid, duplicate, and suppressed addresses.
- Approved recipients are stored with `source=owner_provided`.
- Dry-run warmup schedule preview.
- Owner command `PREPARE WARMUP` uses the real approved env+DB pool count.
- Owner command `START WARMUP DAY=1` now has a real send executor, but only after all gates pass.

## Day Caps

- Day 1: `5`
- Day 2: `10`
- Day 3: `15`
- Day 4-7: `25`

## Day 1 Send Gate

Required before any warmup send:

- approved warmup recipient pool exists
- mail QA decision is `PASS`
- deliverability diagnostics have no blocking failure
- authenticated owner command approves `START WARMUP DAY=1`
- daily cap enforced at `5`

Current result:

- Warmup recipient pool count: `0`
- Warmup recipient pool count after import: `7`
- Runtime warmup import accepted: `7`
- Runtime warmup import rejected: `0`
- Warmup day 1 sent: `0`
- Warmup status: `warmup_day_1_blocked`
- Bounce count after inbox poll: `2`

## Stop Conditions

- bounce
- spam signal
- auth failure
- TLS failure
- DKIM failure
- DMARC failure

## Decision

`BLOCKED_DELIVERABILITY_FAILURE`
