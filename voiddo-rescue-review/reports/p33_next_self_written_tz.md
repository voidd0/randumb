# P33 Self-Written TZ — Mailer Ops Result Retention And Audit Trail

Generated: 2026-05-26 22:59 IDT

## Goal

Keep a useful audit trail for no-send mailer ops runs without leaking raw recipients or letting synthetic test data pollute runtime state.

## Tasks

1. Add `is_synthetic` and `source` fields or equivalent metadata to `mailer_ops_runs`.
2. Mark pytest/admin-test runs synthetic where possible.
3. Preserve real admin ops runs but keep reports sanitized.
4. Add summary counters:
   - total real ops runs
   - total synthetic ops runs
   - latest real ops run
   - blocked unsafe ops count
5. Add cleanup helper for synthetic test runs only.
6. Update admin panel to show real/synthetic separation.
7. Add tests:
   - synthetic runs can be cleaned without deleting real runs
   - real runs remain sanitized
   - admin summary separates real and synthetic counts
   - unknown actions remain blocked
8. Run Huanshu and extra visual plugins on admin.
9. Update reports:
   - `reports/p33_mailer_ops_retention_audit_report.md`

## Acceptance

- At least 230 tests pass.
- Huanshu PASS for authenticated admin.
- Extra visual/accessibility plugins PASS with 0 blockers.
- Real runtime customer SMTP sends remain `0`.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.

