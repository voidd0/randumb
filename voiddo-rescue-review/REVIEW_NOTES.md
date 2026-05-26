# Vøiddo Rescue P2 Mail Trust, Checkout, Warmup Review Notes

Original ZIP path on VPS: `/opt/voiddo-rescue/storage/exports/voiddo-rescue-mvp-p2-mail-checkout-warmup-2026-05-26.zip`

SHA256: `00fd411c363236bb7ebd1bdd6a3ef692289ceb1a89071ebab1c1d2995bb52cff`

## Scope

This branch exposes the Vøiddo Rescue MVP/P2 source tree as normal repository files for review under:

`voiddo-rescue-review/`

## Included

- `docker-compose.yml`
- `.env.example`
- API, web, worker, admin/customer surfaces
- migrations and tests
- WP plugin skeleton
- scripts
- deploy/nginx Rescue route configs
- redacted reports
- Huanshu local adapter scripts
- P2 Mailcow TLS plan/report, without cert backups
- filelist and SHA report

## Excluded

- `.env`
- mailbox/API secrets and passwords
- Mailcow TLS backup private keys under `backups/`
- `node_modules`
- `.next`
- Python cache files
- runtime screenshot/audit/export/report storage
- PNG visual QA artifacts
- logs

## Secret Scan Result

PASS. No raw secrets, mailbox passwords, private owner address, env files, GitHub token, or Mailcow certificate private key backups are included.

## Safety Result

- Live outreach sent: 0
- Warmup sent: 0
- Diagnostic deliverability sends: 0
- Existing non-Rescue app projects were not modified by this source export.
- Owner command source uses runtime `OWNER_COMMAND_EMAIL`; no private owner address is included in this review artifact.

## Current Launch Blockers

- Approved deliverability test inbox pool is missing.
- Approved warmup recipient pool is missing.
- Paddle hosted checkout base URL/client checkout configuration is missing.

## Commit SHA

The pushed branch HEAD is reported in the final operator response after commit creation.
