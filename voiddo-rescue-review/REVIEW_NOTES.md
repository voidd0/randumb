# Vøiddo Rescue P1 Launch-Gated Review Notes

Original ZIP path on VPS: `/opt/voiddo-rescue/storage/exports/voiddo-rescue-mvp-p1-launch-gated-2026-05-26.zip`

SHA256: `c3cd6b5a4040f9863d7c79f428e8e99171a78520c15851e7b9e871a96b837fb1`

## Scope

This branch exposes the Vøiddo Rescue MVP/P1 source tree as normal repository files for review under:

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
- filelist and SHA report

## Excluded

- `.env`
- mailbox/API secrets and passwords
- `node_modules`
- `.next`
- Python cache files
- runtime screenshot/audit/export storage
- PNG visual QA artifacts
- logs

## Secret Scan Result

PASS. No raw secrets, mailbox passwords, private owner address, or env files are included.

## Safety Result

- Live outreach sent: 0
- Warmup sent: 0
- Existing non-Rescue projects were not modified by this source export.
- Owner command source uses runtime `OWNER_COMMAND_EMAIL`; no private owner address is included in this review artifact.

## Known Launch Blockers

- Strict SMTP/IMAP TLS still fails until shared Mailcow serves a trusted certificate.
- Approved deliverability test inbox pool is missing.
- Approved warmup recipient pool is missing.
- Paddle hosted checkout base URL/client checkout configuration is missing.

## Commit SHA

The pushed branch HEAD is reported in the final operator response after commit creation.
