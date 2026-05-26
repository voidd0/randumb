# P2 Mail Trust, Checkout, Warmup Prep Report

Updated: 2026-05-26 12:05 IDT

## Completed

- Created Mailcow TLS backup and pre-change plan in `mailcow_tls_fix_plan.md`.
- Copied the existing trusted Let’s Encrypt certificate for `mail.voiddo.com` into Mailcow `data/assets/ssl/` as real files, not symlinks.
- Restarted only Mailcow certificate consumers:
  - `postfix-mailcow`
  - `dovecot-mailcow`
  - `nginx-mailcow`
- Verified SMTP STARTTLS and IMAP TLS now serve the trusted Let’s Encrypt certificate.
- Verified Rescue strict SMTP and IMAP login pass.
- Verified all `voiddorescue.com` mailboxes can log in over strict IMAP.
- Verified existing `em@voiddo.com` SMTP/IMAP login still passes strict TLS.
- Removed web admin query-token auth.
- API admin auth accepts `X-Admin-Token`, Bearer, and Basic.
- Added `TEST_INBOX_POOL` and `WARMUP_RECIPIENT_POOL` config support.
- Added deliverability diagnostic support with neutral content and max one diagnostic per approved test inbox.
- Added warmup recipient pool counting, suppression filtering, and dry-run schedule previews.
- Added persistent runtime pause controls for owner commands.
- `REPORT TODAY` now writes a report artifact under private runtime storage.

## Verification

- Web admin no auth: `401`
- Web admin query token: `401`
- Web admin Bearer: `200`
- Web admin Basic: `200`
- Public routes still pass.
- API tests: `30 passed`
- Smoke script: `30 passed`
- Rescue mail QA:
  - SMTP strict TLS login: `ok`
  - IMAP strict TLS login: `ok`
  - Decision: `FAIL_BLOCK_LAUNCH` only because approved deliverability test inbox pool is missing.

## Remaining Blockers

- Approved deliverability test inbox pool is missing.
- Approved warmup recipient pool is missing.
- Paddle hosted checkout base URL/client checkout config is missing.

## Safety

- Live outreach sent: `0`
- Warmup sent: `0`
- Sales deliverability messages sent: `0`
- Diagnostic deliverability messages sent: `0`
- No `.env`, mailbox passwords, or raw secrets are included in exports/reports.
- Existing non-Rescue app projects were not modified.

