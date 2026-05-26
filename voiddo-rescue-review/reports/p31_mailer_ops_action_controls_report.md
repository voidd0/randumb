# P31 Mailer Ops Action Controls Report

Generated: 2026-05-26 22:50 IDT

## Scope

P31 added protected operator controls for safe mailer operations in the admin dashboard. The controls run no-send actions by default and record sanitized system events.

## Implemented Controls

- Run customer mail simulation
- Run closed-loop dry run
- Run customer transport dry run
- Prepare owner report action

## Files Changed

- `apps/api/app/mailer_ops_actions.py`
- `apps/api/app/main.py`
- `apps/api/tests/test_p31_mailer_ops_action_controls.py`
- `apps/web/app/admin/page.tsx`
- `apps/web/app/styles.css`

## Safety Behavior

- admin auth required: `true`
- raw recipients in summaries: `false`
- real SMTP default: `false`
- live outreach allowed: `false`
- warmup forced: `false`
- unknown/unsafe action handling: blocked
- shell execution path: absent

## Verification

- focused P30/P31 tests: `8 passed`
- full API test suite: `222 passed`
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
- required action buttons visible: `4/4`

## Runtime Counters After Cleanup

- scheduled warmup: `28`
- warmup sent: `0`
- live outreach sent: `0`
- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- ops action system events: `0`
- bounce/DSN count in last 24h: `2`
- SMTP rate-limit count in last 24h: `1`

## Decision

P31 PASS. The admin control room can now trigger safe no-send mailer operations without unlocking customer SMTP, warmup, auto-replies, or live outreach.

