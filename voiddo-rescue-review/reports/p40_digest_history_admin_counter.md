# P40 Digest History Admin Counter

Generated: 2026-05-27 00:18 IDT

## Scope

P40 exposed sanitized digest history evidence in the protected admin Daily Digest Evidence panel.

## Changes

- Admin dashboard now shows:
  - digest report history row count
  - latest digest history no-send state
  - raw recipients in digest history omitted
- No file contents, raw recipients, owner personal address, message bodies, secrets, or mailbox passwords are exposed.

## Verification

- full smoke/API suite: `254 passed`
- Next production build: PASS
- Huanshu local adapter on authenticated admin screenshots: PASS
- Playwright desktop/mobile admin check: PASS
- axe-core Playwright: PASS, `0` violations
- pa11y WCAG2AA: PASS, `0` errors
- API/web/worker/postgres/redis: healthy

## Runtime State

- digest report history rows retained: `2`
- warmup sent count: `0`
- live outreach sent count: `0`
- mailer action queue after cleanup: `0`
- mailer send ledger after cleanup: `0`
- recipient resolver audit after cleanup: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P40 PASS. This is admin observability only and does not unlock sending.
