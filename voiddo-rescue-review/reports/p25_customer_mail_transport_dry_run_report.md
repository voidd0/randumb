# P25 Customer Mail Transport Dry-Run Boundary Report

Generated: 2026-05-26 21:45 IDT

## Scope

P25 adds a dry-run transport boundary for customer mail actions. It converts `send_ready` actions to `dry_run_recorded` records with sanitized delivery evidence, without calling SMTP.

## Files Changed

- `apps/api/app/mailer_action_queue.py`
- `apps/api/app/main.py`
- `apps/api/tests/test_p25_customer_mail_transport_dry_run.py`

## API

- `POST /admin/mailer/action-queue/transport-dry-run`
- auth: required
- SMTP called: `false`
- live outreach allowed: `false`

## Dry-Run Result Fields

- synthetic Message-ID under `voiddorescue.local`
- subject length
- body length
- template key
- `send_mail=false`
- `smtp_called=false`
- `raw_recipient_included=false`

## Verification

- focused P25 tests: `4 passed`
- full API tests: `190 passed`
- smoke script: PASS, output `ok`
- synthetic queue/test data cleanup: completed

## Runtime Snapshot

- queued: `0`
- prepared: `0`
- blocked: `0`
- send_ready: `0`
- dry_run_recorded: `0`
- sent: `0`

## Safety

No SMTP send occurred. No live outreach was sent. No warmup was forced. Real customer mail transport remains disabled until a later explicit gate adds real-send capability.

