# P44 Mailer Digest Retention Admin Visibility

Generated: 2026-05-27 00:47 IDT

## Scope

P44 exposes digest history cleanup in the protected admin Mailer Ops Controls panel.

## Changes

- Added a protected admin form button for `digest_history_cleanup`.
- Added endpoint regression coverage proving the action stays no-send and persisted.
- Ran the protected action once through the admin API to retain real no-send ops evidence.
- Verified the authenticated admin latest ops list shows `digest history cleanup`.

## Verification

- focused mailer ops tests: `11 passed`
- full smoke/API suite: `266 passed`
- Next production build: PASS
- Playwright desktop/mobile admin visual QA: PASS
- axe: PASS
- pa11y: PASS
- Huanshu local adapter: PASS
- API/web/worker/postgres/redis: healthy

## Runtime State

- retained mailer ops run rows: `1`
- latest retained ops action: `digest_history_cleanup:completed:send=false`
- mailer action queue: `0`
- mailer send ledger: `0`
- recipient resolver audit: `0`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P44 PASS. Digest retention cleanup is now visible and triggerable from the protected admin control room while remaining no-send.
