# Vøiddo Rescue P3 Checkout, Deliverability, Warmup Review Notes

Original ZIP path on VPS: `/opt/voiddo-rescue/storage/exports/voiddo-rescue-mvp-p3-checkout-deliverability-warmup-2026-05-26.zip`

SHA256: `b3cdb5c063438082791a487dfebf5aa8a6b5168a241c25b8beb3b980c39e8b66`

## Scope

This branch exposes the Vøiddo Rescue MVP/P3 source tree as normal repository files for review under:

`voiddo-rescue-review/`

## Included

- `docker-compose.yml`
- `.env.example`
- API, web, worker, admin/customer/checkout surfaces
- migrations and tests
- WP plugin skeleton
- scripts
- deploy/nginx Rescue route configs
- redacted reports
- Huanshu local adapter scripts
- filelist and SHA report

## Excluded

- `.env`
- mailbox/API secrets and passwords
- Mailcow TLS backup private keys under `backups/`
- `node_modules`
- `.next`
- Python cache files
- runtime screenshot/audit/export/report/visual QA storage
- PNG visual QA artifacts
- logs

## Secret Scan Result

PASS. No raw secrets, mailbox passwords, private owner address, env files, GitHub token, Paddle API key, or Mailcow certificate private key backups are included.

## Safety Result

- Live outreach sent: 0
- Warmup sent: 0
- Diagnostic deliverability sends: 0
- Existing non-Rescue app projects were not modified by this source export.
- Owner command source uses runtime `OWNER_COMMAND_EMAIL`; no private owner address is included in this review artifact.

## Current Launch State

`CHECKOUT_READY_NOT_WARMED`

Remaining blockers:

- Approved deliverability test inbox pool is missing.
- Approved warmup recipient pool is missing.

## Commit SHA

The pushed branch HEAD is reported in the final operator response after commit creation.
