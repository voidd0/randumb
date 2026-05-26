# P33 Mailer Ops Retention And Audit Trail Report

Generated: 2026-05-26 23:08 IDT

## Scope

P33 separated synthetic mailer ops runs from real admin-triggered audit history.

## Database Changes

- migration: `026_mailer_ops_run_retention.sql`
- `mailer_ops_runs.is_synthetic`
- `mailer_ops_runs.source`
- indexes:
  - `idx_mailer_ops_runs_synthetic_created`
  - `idx_mailer_ops_runs_source_created`

## Files Changed

- `apps/api/migrations/026_mailer_ops_run_retention.sql`
- `apps/api/app/mailer_ops_actions.py`
- `apps/api/app/main.py`
- `apps/api/tests/test_p33_mailer_ops_retention_audit.py`
- `apps/web/app/admin/page.tsx`

## Safety Behavior

- synthetic runs can be cleaned separately: `true`
- real run history can be retained: `true`
- raw recipients in summaries: `false`
- unknown/unsafe actions remain blocked: `true`
- real SMTP default: `false`
- live outreach allowed: `false`
- warmup forced: `false`

## Verification

- focused P32/P33 tests: `8 passed`
- full API test suite: `230 passed`
- smoke script: PASS, output `ok`
- migration applied: PASS
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

## Runtime Counters After Cleanup

- scheduled warmup: `28`
- warmup sent: `0`
- live outreach sent: `0`
- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- mailer ops run rows: `0`
- bounce/DSN count in last 24h: `2`
- SMTP rate-limit count in last 24h: `1`

## Decision

P33 PASS. The autonomous mailer now has real/synthetic ops run separation and a safe cleanup boundary for test artifacts.

