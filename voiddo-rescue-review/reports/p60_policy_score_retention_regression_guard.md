# P60 Policy Score Retention and Regression Guard

Generated: 2026-05-27 04:53 IDT

## Self-Written Task

Bound `mailer_policy_score_history` growth and add a no-send regression guard that creates review evidence if the latest policy score drops from a clean baseline.

## Implementation

- `apps/api/app/mailer_control_room.py`
  - Added `mailer_policy_score_retention_summary()`.
  - Added `cleanup_mailer_policy_score_history(keep=120)`.
  - Added `mailer_policy_score_regression_guard()`.
  - Added `latest_mailer_policy_score_regression_guard_summary()`.
- `apps/api/app/autonomous_agents.py`
  - Added `mailer_policy_score_retention_agent`.
  - Added `mailer_policy_score_regression_guard_agent`.
  - Runs both after `mailer_policy_score_agent` in the daily loop.
- `apps/api/app/main.py`
  - Added protected policy score retention and regression-guard endpoints.
- `apps/web/app/admin/page.tsx`
  - Shows policy score retained rows, retention no-send state, regression guard decision/count/drop, review task state, and redaction flags.
- `apps/api/tests/test_p36_mailer_digest_scheduler_agent.py`
  - Added tests for retention cleanup, regression pass, regression review-task creation, endpoint auth, latest-summary fail-closed state, and daily-loop order.

## Audit

- Regression guard creates only system-event/Codex-task review evidence.
- Regression guard does not send mail.
- Retention cleanup does not touch send ledgers, queues, or non-Rescue systems.
- Admin shows compact state only; no raw JSON, raw recipients, paths, or secrets.
- Live outreach and warmup send counts remain zero.

## Verification

- targeted P60 tests: `36 passed`
- full API tests: `308 passed`
- smoke: `308 passed, ok`
- Next production build: `PASS`
- Huanshu local adapter: `PASS`
- Playwright desktop/mobile: `PASS`
- axe violations: `0`
- pa11y issues: `0`

## Runtime State

- mailer ops retention history rows: `1`
- mailer digest history rows: `2`
- mailer policy score history rows: `3`
- mailer digest trend guard agent runs: `2`
- mailer policy score agent runs: `3`
- mailer policy score retention agent runs: `2`
- mailer policy score regression guard agent runs: `2`
- regression guard decision: `PASS_NO_SEND`
- regression count: `0`
- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- warmup sent count: `0`
- live outreach sent count: `0`

## Decision

`PASS_NO_SEND`. P60 adds bounded policy history and no-send regression alerts while preserving launch gates.
