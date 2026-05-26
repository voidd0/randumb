# Warmup Readiness Report

Updated: 2026-05-26 12:45 IDT

## Status

Warmup is prepared in dry-run only and has not started.

Current blocker:

- Owner has not provided an approved warmup recipient pool.
- Deliverability test pool is missing.

## Daily Cap Model

- Day 1: 5-10
- Day 2: 10-15
- Day 3: 15-25
- Day 4-7: 25-40

The implemented dry-run planner stores the conservative lower bound for each day.

## Implemented

- `WARMUP_RECIPIENT_POOL` env/config support.
- Protected import endpoint: `POST /warmup/recipients/import`.
- Suppression-list filtering.
- Dry-run schedule preview.
- Owner command `PREPARE WARMUP` uses real env+DB approved pool count.
- Owner command `START WARMUP DAY=1` is implemented but remains blocked until all gates pass.

## Stop Conditions

- Bounce signal
- Spam signal
- Auth failure
- TLS failure
- DKIM failure
- DMARC failure

## Decision

`BLOCKED_NO_RECIPIENT_POOL`

No warmup messages were sent.
