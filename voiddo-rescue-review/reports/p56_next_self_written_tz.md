# P56 Next Self-Written TZ

Generated: 2026-05-27 03:16 IDT

## Task

Expose the compact latest trend-guard summary in the protected admin dashboard Mailer/Daily Digest evidence area, with Huanshu and secondary visual checks.

## Required Work

1. Fetch `GET /admin/mailer/digest-trend-guard/latest` from the admin page.
2. Display only compact evidence:
   - latest decision
   - regression count
   - queue/ledger/resolver zero-state
   - latest run timestamp
   - no-send/privacy/secret flags
3. Do not display raw history rows, raw JSON, report paths, recipient data, owner personal address, or secrets.
4. Add or update tests for API auth/redaction as needed.
5. Rebuild web, run full API tests and smoke.
6. Run Huanshu + Playwright desktop/mobile + axe + pa11y on authenticated admin.
7. Export clean review package and update memories.

## Non-Negotiables

- no cold outreach
- no forced warmup
- no customer-facing auto-replies
- no `.env` or secrets in review artifacts
- non-Rescue projects untouched
