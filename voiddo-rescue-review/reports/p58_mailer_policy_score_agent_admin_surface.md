# P58 Mailer Policy Score Agent Admin Surface

Generated: 2026-05-27 04:07 IDT

## Self-Written Task

Promote the mailer policy score from a protected endpoint into the autonomous operating loop and surface the compact redacted score in the protected admin Daily Digest Evidence panel.

## Implementation

- `apps/api/app/autonomous_agents.py`
  - Added `mailer_policy_score_agent`.
  - Added the agent to `run_daily_loop()` immediately after `mailer_digest_trend_guard_agent`.
- `apps/web/app/admin/page.tsx`
  - Fetches protected `/admin/mailer/policy-score`.
  - Displays score, decision, blocker count, next safe action, mail QA decision, queue rows, no-send state, raw-recipient omission, and secret omission.
- `apps/api/tests/test_p36_mailer_digest_scheduler_agent.py`
  - Added coverage for the policy score agent and daily-loop ordering.

## Audit

- Admin auth remains required.
- Policy score output stays compact and redacted.
- No raw recipient addresses, report paths, secrets, raw JSON, or mailbox credentials are rendered.
- No SMTP send path was enabled.
- Live outreach and warmup send counts remain zero.

## Verification

- targeted P58 tests: `45 passed`
- full API tests: `299 passed`
- smoke: `299 passed, ok`
- Next production build: `PASS`
- Huanshu local adapter: `PASS`
- Playwright desktop/mobile: `PASS`
- axe violations: `0`
- pa11y issues: `0`
- policy score: `100`
- policy decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`

## Runtime State

- mailer ops retention history rows: `1`
- mailer digest history rows: `1`
- mailer digest trend guard agent runs: `1`
- mailer policy score agent runs: `1`
- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- warmup sent count: `0`
- live outreach sent count: `0`

## Decision

`PASS_NO_SEND`. P58 makes policy score evidence part of the autonomous loop and visible to the operator while preserving no-send, privacy, and launch-gate constraints.
