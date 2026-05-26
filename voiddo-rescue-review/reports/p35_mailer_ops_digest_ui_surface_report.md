# P35 Mailer Ops Digest UI Surface Report

Generated: 2026-05-26 23:24 IDT

## Scope

P35 exposed daily digest mailer ops evidence in the protected admin dashboard without adding send controls.

## Files Changed

- `apps/api/app/mailer_control_room.py`
- `apps/api/app/main.py`
- `apps/api/tests/test_p35_mailer_ops_digest_ui_surface.py`
- `apps/web/app/admin/page.tsx`

## Admin Evidence Added

- daily digest owner report action status
- mailer ops real count in digest
- mailer ops synthetic count in digest
- blocked unsafe ops count in digest
- latest owner report generated state
- daily digest email send state
- digest raw-recipient privacy state

## Verification

- focused P34/P35 tests: `8 passed`
- full API test suite: `238 passed`
- smoke script: PASS, output `ok`
- Next production build: PASS
- Huanshu local adapter: PASS
- Playwright desktop screenshot: nonblank
- Playwright mobile screenshot: nonblank
- axe-core: PASS, 0 violations
- pa11y: PASS, 0 issues
- horizontal overflow: `false`
- broken images: `0`
- unresolved template variables: `false`
- raw email-like recipient text: `false`
- daily digest panel visible: `true`
- no-send status visible: `true`

## Runtime Counters After Cleanup

- warmup sent: `0`
- live outreach sent: `0`
- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- mailer ops run rows: `0`
- bounce/DSN count in last 24h: `2`
- SMTP rate-limit count in last 24h: `1`

## Decision

P35 PASS. The admin control room now shows mailer ops daily digest evidence while every send gate remains closed.

