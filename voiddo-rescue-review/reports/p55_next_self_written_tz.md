# P55 Next Self-Written TZ

Generated: 2026-05-27 03:03 IDT

## Task

Add a compact protected admin/API summary for the latest mailer digest trend guard agent run without exposing raw history rows, recipients, secrets, or send capability.

## Required Work

1. Add a sanitized latest trend-guard agent summary to an existing protected mailer endpoint, or create a narrow protected endpoint if cleaner.
2. Include only:
   - latest decision
   - regression count
   - queue/ledger/resolver zero-state
   - latest run timestamp
   - no-send/privacy/secret flags
3. Add tests for auth, no-send flags, redaction, and fail-closed behavior.
4. If web UI changes, run Huanshu + Playwright + axe + pa11y.
5. Run full API tests and smoke.
6. Export clean review package and update memories.

## Non-Negotiables

- no cold outreach
- no forced warmup
- no customer-facing auto-replies
- no `.env` or secrets in review artifacts
- non-Rescue projects untouched
