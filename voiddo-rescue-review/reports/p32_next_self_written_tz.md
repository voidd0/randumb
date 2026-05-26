# P32 Self-Written TZ — Mailer Ops Result Persistence

Generated: 2026-05-26 22:50 IDT

## Goal

Persist sanitized results from admin-triggered no-send mailer ops actions in a dedicated table instead of relying only on generic system events.

## Tasks

1. Add migration for `mailer_ops_runs`:
   - id
   - action
   - status
   - result_json
   - raw_recipient_addresses_included
   - send_mail
   - smtp_called
   - live_outreach_allowed
   - created_at
2. Make `run_mailer_ops_action()` write one row per run.
3. Add protected summary endpoint counts by action/status.
4. Update admin panel to show latest ops run status and action history.
5. Add tests:
   - ops run rows are written
   - summaries omit raw recipients
   - unknown actions persist as blocked
   - live outreach remains blocked
6. Run Huanshu and extra visual plugins on the updated admin page.
7. Update reports:
   - `reports/p32_mailer_ops_result_persistence_report.md`

## Acceptance

- At least 226 tests pass.
- Huanshu PASS for authenticated admin.
- Extra visual/accessibility plugins PASS with 0 blockers.
- Real runtime customer SMTP sends remain `0`.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.

