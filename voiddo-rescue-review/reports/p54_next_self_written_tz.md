# P54 Next Self-Written TZ

Generated: 2026-05-27 02:49 IDT

## Task

Wire the mailer digest trend guard into the autonomous daily loop and admin evidence surfaces without enabling any send path.

## Required Work

1. Add `mailer_digest_trend_guard_agent` to `run_agent()` and `run_daily_loop()`.
2. Persist its latest run in `agent_runs` with compact no-send evidence.
3. Add protected admin evidence only if the data is already present in existing panels; otherwise keep it API/report-only.
4. Update runtime and launch reports with latest trend guard decision.
5. Add tests:
   - agent exists and returns `PASS_NO_SEND` on clean history
   - agent returns `FAIL_BLOCK_LAUNCH` on queue regression
   - daily loop runs trend guard after retention/digest evidence
   - no send capability, no raw recipients, no secrets
6. Run full API tests and smoke.
7. If UI changes, run Huanshu + Playwright + axe + pa11y.

## Non-Negotiables

- no cold outreach
- no forced warmup
- no customer-facing auto-replies
- no `.env` or secrets in review artifacts
- non-Rescue projects untouched
