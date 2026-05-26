# P43 Mailer Digest Retention Ops Evidence

Generated: 2026-05-27 00:51 IDT

## Scope

P43 records digest history cleanup as a persisted no-send mailer operations action.

## Changes

- Added `digest_history_cleanup` to allowed mailer ops actions.
- `run_mailer_ops_action("digest_history_cleanup")` runs `cleanup_mailer_digest_history(90)`.
- Persisted evidence includes:
  - action
  - status
  - send_mail false
  - smtp_called false
  - live_outreach_allowed false
  - deleted_count
  - before_total_rows
  - after_total_rows

## Verification

- focused mailer ops tests: `15 passed`
- full smoke/API suite: `265 passed`
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

P43 PASS. Digest retention cleanup is now auditable in mailer ops evidence and remains no-send.
