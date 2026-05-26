# P42 Digest Retention Agent

Generated: 2026-05-27 00:38 IDT

## Scope

P42 wired digest history retention cleanup into the autonomous agent loop as no-send housekeeping.

## Changes

- Added `mailer_digest_retention_agent` to `run_agent()`.
- Added `mailer_digest_retention_agent` to `run_daily_loop()`.
- The agent runs `cleanup_mailer_digest_history(90)` and returns before/after retention summaries with send flags false.

## Verification

- focused digest/agent tests: `28 passed`
- full smoke/API suite: `262 passed`
- API/web/worker/postgres/redis: healthy

## Runtime State

- digest report history rows retained: `2`
- mailer action queue after cleanup: `0`
- mailer send ledger after cleanup: `0`
- recipient resolver audit after cleanup: `0`
- mailer ops runs after cleanup: `0`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P42 PASS. Digest history retention now runs in the autonomous daily loop without sending mail or touching send-related ledgers.
