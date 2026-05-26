# P53 Next Self-Written TZ

Generated: 2026-05-27 02:31 IDT

## Task

Build a no-send mailer digest trend guard that lets the autonomous system compare the latest digest/retention evidence against recent history and detect regressions before any mail path is allowed to progress.

## Required Work

1. Add a protected digest trend summary endpoint or extend the existing digest summary with recent history trend fields.
2. Track:
   - digest history row count
   - ops retention history row count
   - latest no-send state
   - latest privacy flags
   - latest secrets flags
   - queue/ledger/resolver zero-state
3. Add tests proving trend summaries do not expose raw recipients, secrets, mailbox passwords, or send capability.
4. Surface the trend guard in protected admin if it changes UI.
5. Run full tests, smoke, Huanshu, Playwright, axe, and pa11y for any UI change.
6. Export a clean review package and update memories.

## Non-Negotiables

- no cold outreach
- no warmup forcing
- no customer-facing auto-replies
- no `.env` or secrets in review artifacts
- non-Rescue projects untouched
