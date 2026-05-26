# Vøiddo Rescue Review Notes

Generated: 2026-05-27 00:47 IDT

## Source

- Source tree: `/opt/voiddo-rescue`
- Review folder: `voiddo-rescue-review/`
- Branch: `voiddo-rescue-mvp-review-20260526-files`
- Current completed pass: P44 Mailer Digest Retention Admin Visibility

## Included

- Application source
- Docker Compose config
- Migrations
- Scripts
- WordPress plugin source
- Redacted reports
- `.env.example`
- `ARCHIVE_FILELIST.txt`
- `ARCHIVE_SHA256.txt`

## Excluded

- `.env`, `*.env`, mailbox passwords, private keys, raw secrets
- `.venv`, `venv`, `.pytest_cache`, `__pycache__`, `*.pyc`
- `node_modules`, `.next`
- runtime `storage`, `exports`, `screenshots`, `logs`, `backups`
- visual QA PNG screenshots

## Secret Scan

Secret and artifact scans are required before every push. P44 scan result: clean.

## Runtime Status

- live outreach sent: `0`
- warmup sent: `0`
- retained mailer ops evidence: `digest_history_cleanup:completed:send=false`
- launch state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Commit

The exact branch commit SHA is returned by `git rev-parse HEAD` after the P44 commit and push.
