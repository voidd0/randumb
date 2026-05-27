# P63 Next Self-Written TZ

Generated: 2026-05-27 05:54 IDT

## Objective

Build a self-audit coverage matrix for the autonomous mailer so every inbound and outbound path has an explicit verifier before it can affect a customer or owner-visible report.

## Scope

1. Add `mailer_self_audit_matrix` persistence for inbound classification, reply action gating, owner command gating, queue hygiene, policy score, KPI trend, warmup state, and no-send proof.
2. Add `mailer_self_audit_matrix_agent` after `mailer_business_kpi_agent`.
3. Add protected API evidence and report rows for the matrix.
4. Add tests proving every current mailer agent has a matrix row and no unchecked output path can send mail.
5. Keep live outreach disabled and do not force warmup sends.

## Acceptance

- Matrix rows persist and are retained.
- Daily loop includes the matrix agent after KPI trend.
- Reports include matrix coverage.
- No raw recipient addresses, secrets, or private owner email appear in package files.
- Full tests and smoke pass.
- Live outreach remains `0`.
- Warmup sends are not forced manually.
