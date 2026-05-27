# P58 Next Self-Written TZ

Generated: 2026-05-27 03:47 IDT

## Task

Wire the no-send mailer policy score into the autonomous agent loop and protected admin evidence without enabling any send path.

## Required Work

1. Add `mailer_policy_score_agent` to `run_agent()` and `run_daily_loop()`.
2. Expose latest policy score in protected admin Mailer/Daily Digest evidence.
3. Add tests:
   - agent exists and returns no-send score
   - daily loop runs policy score after trend guard
   - admin endpoint remains protected
   - no raw recipients/secrets/send flags
4. Rebuild API/web.
5. Run full API tests and smoke.
6. Because admin UI changes, run Huanshu + Playwright desktop/mobile + axe + pa11y.
7. Export clean review package and update memories.

## Non-Negotiables

- no cold outreach
- no forced warmup
- no customer-facing auto-replies
- no `.env` or secrets in review artifacts
- non-Rescue projects untouched
