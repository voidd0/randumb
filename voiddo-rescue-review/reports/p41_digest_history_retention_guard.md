# P41 Mailer Digest Daily Loop Retention Guard

Generated: 2026-05-27 00:27 IDT

## Scope

P41 added bounded retention guardrails for the sanitized `mailer_digest_reports` history table.

## Changes

- Added `mailer_digest_retention_summary()`.
- Added `cleanup_mailer_digest_history(keep=90)`.
- Added protected `POST /admin/mailer/digest-history/cleanup`.
- `mailer_digest_summary()` now includes sanitized retention summary metadata.

## Verification

- focused digest/retention tests: `24 passed`
- full smoke/API suite: `258 passed`
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

P41 PASS. Digest history now has no-send retention cleanup without touching the mailer action queue, send ledger, recipient resolver audit, or any send path.
