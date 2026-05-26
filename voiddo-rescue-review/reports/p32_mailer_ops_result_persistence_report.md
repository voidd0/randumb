# P32 Mailer Ops Result Persistence Report

Generated: 2026-05-26 22:59 IDT

## Scope

P32 moved admin-triggered no-send mailer operation evidence into a dedicated audited table instead of relying only on generic system events.

## Database Changes

- migration: `025_mailer_ops_runs.sql`
- table: `mailer_ops_runs`
- indexes:
  - `idx_mailer_ops_runs_action_created`
  - `idx_mailer_ops_runs_status_created`

## Files Changed

- `apps/api/migrations/025_mailer_ops_runs.sql`
- `apps/api/app/mailer_ops_actions.py`
- `apps/api/tests/test_p32_mailer_ops_result_persistence.py`
- `apps/web/app/admin/page.tsx`

## Safety Behavior

- run result persistence: implemented
- unknown actions persisted as blocked: `true`
- raw recipients in summaries: `false`
- real SMTP default: `false`
- live outreach allowed: `false`
- warmup forced: `false`

## Verification

- focused P31/P32 tests: `8 passed`
- full API test suite: `226 passed`
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

P32 PASS. The autonomous mailer now has a dedicated no-send ops result persistence boundary, while runtime send gates remain closed.

