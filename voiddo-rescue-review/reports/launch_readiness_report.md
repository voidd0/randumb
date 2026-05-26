# Vøiddo Rescue Launch Readiness Report

Generated: 2026-05-26

## Current Status

MVP runtime is built and running in an isolated Docker Compose project, but it is not ready for live outreach.

## Passed

- Existing project inventory completed.
- Existing projects were not intentionally modified.
- Rescue project is isolated under `/opt/voiddo-rescue`.
- Docker services are running and healthy.
- Database migrations created the MVP schema.
- API health checks pass.
- Web build and health checks pass.
- Worker health checks pass.
- Safe scanner produced a real audit and screenshots.
- Audit page route exists.
- Admin dashboard route exists.
- Customer dashboard route exists.
- Outreach dry-run preview works.
- Email QA gate works.
- Suppression endpoint works.
- Unsubscribe endpoint works.
- Rate-limit/safety gate blocks live sending while paused.
- Inbox classifier works.
- Paddle products/prices are configured.
- Paddle webhook signature verification works.
- WordPress plugin skeleton syntax check passes.
- Huashu/design-review pre-publish visual gate passes locally.
- Rollback plan exists.

## Blocked Before Live Launch

- DKIM TXT for `voiddorescue.com` is not published.
- DMARC TXT has an invalid trailing `TTL: Automatic` string.
- Strict TLS SMTP/IMAP fails because current Mailcow mail certificate is not valid for `mail.voiddorescue.com`.
- Public reverse proxy routes have not been wired for:
  - `rescue.voiddo.com`
  - `app.rescue.voiddo.com`
  - `api.rescue.voiddo.com`
  - `audit.rescue.voiddo.com`
  - `go.rescue.voiddo.com`
  - `status.rescue.voiddo.com`
- Public-domain screenshot QA has not run yet.
- First 100-150 lead batch has not been generated/scanned.
- First 20 live-send preview has not been approved by launch flag.

## Launch Flags

- `OUTREACH_DRY_RUN=true`
- `OUTREACH_PAUSED=true`
- `AUTO_REPLIES_PAUSED=true`
- `FIRST_LIVE_SEND_FLAG=false`
- `INBOX_WORKER_ENABLED=false`
- `PADDLE_PROVISIONING_PAUSED=true`

These flags must remain conservative until all blockers are cleared.

## Required Owner/DNS Actions

1. Add DKIM TXT:
   - Host: `dkim._domainkey`
   - Value: see `/opt/voiddo-rescue/reports/mailcow_setup_report.md`
2. Fix DMARC TXT:
   - Remove literal ` TTL: Automatic` from the TXT value.
3. Decide whether to add `mail.voiddorescue.com` to the Mailcow certificate/SAN set or use a trusted existing mail hostname for SMTP/IMAP.

## Ready For Next Autonomous Pass

- Reverse proxy route planning without touching existing routes.
- Public-domain dry-run once DNS/TLS blockers are resolved.
- Lead source importer and first batch generation.
- Admin preview queue for the first 20 dry-run emails.
