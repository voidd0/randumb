# P62 Next Self-Written TZ

Generated: 2026-05-27 05:29 IDT

## Objective

Harden the autonomous mailer into a complete closed-loop operator without enabling cold outreach.

## Scope

1. Add a mailer business KPI trend table for replies, safe actions, queued actions, blocked actions, policy score, and warmup state.
2. Add a `mailer_business_kpi_agent` to the daily loop after `policy_trend_reporting_agent`.
3. Add admin/API evidence for latest KPI trend without exposing recipients or secrets.
4. Extend the owner digest payload with compact KPI trend evidence while keeping email sending gated.
5. Add self-audit checks for mailer autonomy coverage: inbound classification, reply action gating, queue hygiene, policy trend, and no-send state.
6. Add tests that the full mailer autonomy loop is observable and still cannot send cold outreach.

## Acceptance

- KPI trend records are persisted and retained.
- Daily loop includes the KPI agent after policy trend reporting.
- Reports include KPI trend evidence.
- No raw recipient addresses, secrets, or owner private email appear in package files.
- Full tests and smoke pass.
- Live outreach remains `0`.
- Warmup sends are not forced manually.
