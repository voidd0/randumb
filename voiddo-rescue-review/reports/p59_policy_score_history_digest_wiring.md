# P59 Policy Score History and Digest Wiring

Generated: 2026-05-27 04:31 IDT

## Self-Written Task

Persist mailer policy score history and wire the latest redacted score into owner digest/runtime/admin evidence so the autonomous mailer can track policy trend instead of only a single current score.

## Implementation

- `apps/api/migrations/029_mailer_policy_score_history.sql`
  - Adds `mailer_policy_score_history` with score, decision, blocker count, mail QA, signal counts, queue hygiene counts, and no-send/privacy flags.
- `apps/api/app/mailer_control_room.py`
  - Adds `record_mailer_policy_score_history()`.
  - Adds `latest_mailer_policy_score_history()`.
  - Adds policy history to `mailer_digest_summary()`, `write_owner_status_report()`, and `write_mailer_digest_agent_report()`.
- `apps/api/app/autonomous_agents.py`
  - Persists policy score history when `mailer_policy_score_agent` completes.
- `apps/api/app/main.py`
  - Adds protected `GET /admin/mailer/policy-score/history`.
- `apps/web/app/admin/page.tsx`
  - Shows policy history row count, latest score, latest decision, no-send state, raw-recipient omission, and secret omission.
- `apps/api/tests/test_p36_mailer_digest_scheduler_agent.py`
  - Adds persistence, endpoint auth/redaction, digest, and report coverage.

## Audit

- History rows are compact and redacted.
- No raw recipients or secrets are stored in report metadata.
- Admin history endpoint requires admin auth.
- Digest includes history evidence without sending mail.
- No live outreach, warmup, auto-reply, or SMTP path was enabled.

## Verification

- targeted P59 tests: `31 passed`
- full API tests: `303 passed`
- smoke: `303 passed, ok`
- Next production build: `PASS`
- Huanshu local adapter: `PASS`
- Playwright desktop/mobile: `PASS`
- axe violations: `0`
- pa11y issues: `0`
- migration applied: `029_mailer_policy_score_history.sql`

## Runtime State

- mailer ops retention history rows: `1`
- mailer digest history rows: `2`
- mailer policy score history rows: `2`
- mailer digest trend guard agent runs: `2`
- mailer policy score agent runs: `2`
- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- policy score: `100`
- policy decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- warmup sent count: `0`
- live outreach sent count: `0`

## Decision

`PASS_NO_SEND`. P59 makes policy score trend evidence durable and visible while preserving privacy, no-send behavior, and launch gates.
