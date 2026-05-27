# P57 Next Self-Written TZ

Generated: 2026-05-27 03:31 IDT

## Task

Start converting the mailer evidence chain into an autonomous action policy score so the system can rank next safe mailer work without enabling any send path.

## Required Work

1. Add a no-send policy score function that combines:
   - latest trend guard decision
   - mail QA state
   - recent bounce/rate-limit/spam signals
   - warmup schedule state
   - queue/ledger/resolver hygiene
2. Return:
   - score 0-100
   - decision label
   - next safe action
   - blockers
   - no-send/privacy/secret flags
3. Add protected API endpoint.
4. Add tests for clean score, blocker score, auth, no-send flags, and redaction.
5. Run full API tests and smoke.
6. UI is optional; if UI changes, run Huanshu + Playwright + axe + pa11y.

## Non-Negotiables

- no cold outreach
- no forced warmup
- no customer-facing auto-replies
- no `.env` or secrets in review artifacts
- non-Rescue projects untouched
