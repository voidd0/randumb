# Vøiddo Rescue Review Notes

Branch: `voiddo-rescue-mvp-review-20260526-files`

Folder: `voiddo-rescue-review/`

Pass: `P60 Policy Score Retention and Regression Guard`

## Original Runtime Path

`/opt/voiddo-rescue`

## Export

- ZIP path: pending generation
- SHA256: see `ARCHIVE_SHA256.txt` and sidecar `.sha256` file generated after packaging

## Included

- `docker-compose.yml`
- `.env.example`
- API, worker, web, admin, shared packages, scripts, migrations, WP plugin source, redacted reports, filelist, and review notes.

## Excluded

- `.env`, `*.env`, mailbox passwords, private keys, raw secrets
- `.venv`, `venv`, `.pytest_cache`, `__pycache__`, `*.pyc`
- `node_modules`, `.next`
- runtime `storage`, `logs`, `backups`, exports, screenshots, visual QA PNG artifacts

## Secret And Artifact Scan

- secret scan: `PASS`
- owner personal email scan: `PASS`
- forbidden artifact scan: `PASS`

## Verification

- targeted P60 tests: `36 passed`
- full API tests: `308 passed`
- smoke: `308 passed, ok`
- Next production build: `PASS`
- Huanshu P60: `PASS`
- Playwright desktop/mobile + axe + pa11y P60: `PASS`

## Runtime Safety

- live outreach sent: `0`
- warmup sent: `0`
- mailer policy score: `100`
- mailer policy history rows: `3`
- policy regression guard: `PASS_NO_SEND`
- non-Rescue projects touched: `no`

## Commit

Recorded in the final operator output and available from branch `HEAD`. This file does not embed its own final commit SHA because changing the file changes the commit hash.
