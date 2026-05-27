# P59 Self-Written TZ: Policy Score History and Digest Wiring

Generated: 2026-05-27 04:07 IDT

## Goal

Persist mailer policy score history and wire the latest score into the daily owner digest and runtime reports so the autonomous mailer can prove whether policy is improving or regressing over time.

## Tasks

1. Add `mailer_policy_score_history` migration/table with score, decision, blocker count, queue hygiene counts, mail QA decision, signal counts, send flags, and redaction flags.
2. Make `mailer_policy_score_agent` persist one compact row per run.
3. Add a protected endpoint for latest/history summary without raw recipients or secrets.
4. Add policy score history rows to the admin Daily Digest Evidence panel.
5. Add policy score trend fields to `write_owner_status_report()`.
6. Add tests for persistence, retention/redaction, endpoint auth, admin visibility, and no-send guarantees.
7. Run full API tests, smoke, Huanshu, Playwright, axe, pa11y, hygiene scan, export, push, and memory updates.

## Acceptance

- Policy score history is persisted and redacted.
- Daily digest includes latest policy score evidence.
- Admin shows latest policy score history without raw rows.
- No SMTP/warmup/outreach sends occur.
- Live outreach remains `0`.
- Non-Rescue projects remain untouched.
