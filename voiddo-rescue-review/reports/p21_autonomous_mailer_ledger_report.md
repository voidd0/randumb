# P21 Autonomous Mailer Ledger Report

Generated: 2026-05-26 20:59 IDT

## Scope

P21 adds a single protected evidence ledger for the autonomous mailer. The ledger joins runtime controls, owner commands, inbound classifications, email events, outbound decisions, mail signals, throttle state, suppression, and warmup calendar state without exposing raw addresses or message bodies.

## Files Changed

- `apps/api/app/mailer_autonomy_ledger.py`
- `apps/api/app/main.py`
- `apps/api/tests/test_p21_mailer_autonomy_ledger.py`
- `apps/web/app/admin/page.tsx`

## API

- `GET /admin/mailer/autonomy-ledger`
- auth: required
- public exposure: none
- raw recipient addresses: omitted
- raw owner address: omitted
- raw message bodies/subjects: omitted

## Current Ledger Snapshot

- policy: `autonomous_mailer_all_io_gated_no_raw_addresses`
- live outreach allowed: `false`
- auto replies allowed: `false`
- owner commands tracked: `772`
- inbound human-review threads: `0`
- throttle states: `0`
- raw addresses included: `false`
- current blockers:
  - `outreach_paused_env`
  - `first_live_send_flag_false`
  - `auto_replies_paused_env`
  - `recent_bounce_or_dsn`
  - `recent_rate_limit`

## Verification

- focused P21 tests: `5 passed`
- full API tests: `172 passed`
- smoke script: PASS, output `ok`
- Huanshu: PASS on landing, audit demo, customer, customer token dashboard, status, unsubscribe, authenticated admin
- extra QA plugins: PASS with `0` blockers
- test data cleanup: completed

## Safety

The ledger is read-only evidence. It does not send mail, does not start warmup, does not enable outreach, and does not expose mailbox credentials or raw recipient addresses.

