# P57 Mailer Policy Score

Generated: 2026-05-27 03:47 IDT

## Self-Written Task

Add a no-send mailer policy score that combines trend guard evidence, mail QA, recent mail signals, warmup schedule state, and queue hygiene to rank the next safe mailer action.

## Implementation

- `apps/api/app/mailer_control_room.py`
  - Added `mailer_policy_score()`.
  - Computes score 0-100.
  - Returns decision label, blockers, next safe action, mail QA state, signal counts, warmup state, queue hygiene, and no-send/privacy flags.
- `apps/api/app/main.py`
  - Added protected `GET /admin/mailer/policy-score`.
- `apps/api/tests/test_p36_mailer_digest_scheduler_agent.py`
  - Added clean score test.
  - Added queue regression score test.
  - Added recent bounce signal score test.
  - Added protected endpoint auth/no-send test.

## Audit

- Endpoint requires admin auth.
- Score is evidence-only and cannot send mail.
- Score blocks on recent bounce/DSN, rate-limit, spam signal, failed trend guard, mail QA failure, queue rows, ledger rows, or resolver audit rows.
- No raw recipients, raw history rows, report paths, secrets, or mailbox passwords are returned.

## Verification

- targeted P57 tests: `43 passed`
- full API tests: `297 passed`
- smoke: `297 passed, ok`
- runtime score: `100`
- runtime decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- runtime blockers: `0`

## Runtime State

- mailer ops retention history rows: `1`
- mailer digest history rows: `1`
- mailer digest trend guard agent runs: `1`
- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- warmup sent count: `0`
- live outreach sent count: `0`

## Decision

`PASS_NO_SEND`. P57 gives the autonomous mailer a policy score for safe next-action selection while preserving launch blocks and no-send constraints.
