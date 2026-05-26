# P52 Mailer Digest Retention-History Admin Visibility

Generated: 2026-05-27 02:31 IDT

## Self-Written Task

Expose the mailer ops retention-history evidence inside the protected Daily Digest Evidence admin panel so the autonomous mailer can prove the daily digest sees retention history, no-send state, privacy flags, and secret flags without expanding send capability.

## Implementation

- `apps/web/app/admin/page.tsx`
  - Reads `digest.mailer_ops_retention_history`.
  - Displays ops retention history row count in Daily Digest Evidence.
  - Displays latest ops retention no-send state.
  - Displays latest retained real ops count.
  - Displays raw-recipient and secret flags.
- `apps/api/tests/test_p35_mailer_ops_digest_ui_surface.py`
  - Adds endpoint/function tests for `mailer_ops_retention_history` in digest summary.
  - Confirms no-send state, no SMTP, no live outreach, no raw recipients, and no secrets.

## Audit

- protected admin auth remains required.
- backend digest summary already exposed sanitized retention-history evidence; no schema change required.
- no outbound transport was enabled.
- no warmup send was forced.
- no raw owner/customer/recipient address was added to reports or review artifacts.

## Verification

- targeted P52 tests: `34 passed`
- full API tests: `284 passed`
- smoke: `284 passed, ok`
- Next production build: `PASS`
- Huanshu local adapter: `PASS`
- Playwright desktop/mobile: `PASS`
- axe violations: `0`
- pa11y issues: `0`

## Runtime State After Cleanup

- mailer ops retention history rows: `1`
- latest retention history: `0:1:0:send=false`
- mailer digest history rows: `1`
- latest digest history: `0:0:email=false`
- mailer action queue rows: `0`
- send ledger rows: `0`
- recipient resolver audit rows: `0`
- warmup sent count: `0`
- live outreach sent count: `0`

## Decision

`PASS_NO_SEND`. P52 improves autonomous mailer evidence visibility and keeps launch readiness at `WARMUP_SCHEDULED_NO_OUTREACH`.
