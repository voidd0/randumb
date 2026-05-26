# P39 Mailer Digest Retention and Historical Evidence

Generated: 2026-05-27 00:07 IDT

## Scope

P39 added a sanitized historical ledger for `mailer_digest_agent` runtime reports.

## Changes

- Added migration `027_mailer_digest_reports.sql`.
- Added `mailer_digest_reports` table.
- `write_mailer_digest_agent_report()` now inserts a compact history row after writing the runtime report.
- `mailer_digest_summary()` now returns sanitized history metadata:
  - count
  - latest row
  - raw_recipient_addresses_included false
  - secrets_included false
- No admin UI change in this pass.

## Verification

- migration applied: `027_mailer_digest_reports.sql`
- focused P35/P36 digest tests: `20 passed`
- full smoke/API suite: `254 passed`
- API/web/worker/postgres/redis: healthy

## Runtime State

- digest report history rows retained: `2`
- warmup sent count: `0`
- live outreach sent count: `0`
- mailer action queue after cleanup: `0`
- mailer send ledger after cleanup: `0`
- recipient resolver audit after cleanup: `0`
- mailer ops runs after cleanup: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P39 PASS. Digest history is now persisted without raw recipients or secrets. This does not unlock warmup, live outreach, auto-replies, or customer SMTP.
