# Vøiddo Rescue MVP Review Notes

Original ZIP path on VPS:
- `/opt/voiddo-rescue/storage/exports/voiddo-rescue-mvp-code-2026-05-26.zip`

Expected SHA256:
- `76fe46d16c5070df639016905bddd9bf9642b7086dd2ade0a2e6722228049f3b`

Target GitHub branch:
- `voiddo-rescue-mvp-review-20260526-files`

Target folder:
- `voiddo-rescue-review/`

Excluded from review tree:
- `.env`
- mailbox passwords and private runtime secrets
- `.venv/`
- `node_modules/`
- `.next/`
- `__pycache__/`
- `*.pyc`
- runtime storage contents
- logs/backups
- PNG screenshots

Included intentionally:
- `.env.example`
- `docker-compose.yml`
- database migrations
- API/web/worker source
- WordPress plugin skeleton
- setup/sync scripts
- redacted reports
- file list and SHA report

Secret scan result:
- `SECRET_SCAN_PASS`
- Token/private-key patterns checked: GitHub PAT, GitHub short tokens, NPM tokens, OpenAI-style keys, private key blocks, npm registry auth tokens.
- Env-like sensitive assignments checked for non-redacted values.
- Forbidden path scan checked for `.env`, `node_modules`, `.next`, `.venv`, `__pycache__`, `*.pyc`, and PNG files.

Confirmation:
- No raw secrets are intentionally included.
- No mailbox passwords are intentionally included.
- No runtime `.env` is included.
- GitHub `main`/`master` is not modified; this review content lives on the dedicated branch only.

Commit SHA:
- Artifact import commit: 
