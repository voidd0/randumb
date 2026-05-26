# P28 Self-Written TZ — Recipient Resolver Vault Boundary

Generated: 2026-05-26 22:01 IDT

## Goal

Implement a safe recipient resolver boundary for customer lifecycle mail so the executor can eventually send to real customers without exposing raw addresses in review exports, public reports, logs, or admin summaries.

## Tasks

1. Add private recipient resolver module.
2. Store raw recipient lookup only in private DB/runtime context, never in review reports.
3. Add resolver audit records with hashes only.
4. Add tests:
   - resolver returns customer email only inside transport boundary
   - resolver output is never included in summaries
   - missing customer blocks send
   - suppressed customer blocks send
   - closed-loop executor still sends 0 under default flags
5. Add report:
   - `reports/p28_recipient_resolver_boundary_report.md`

## Acceptance

- At least 207 tests pass.
- Raw recipient address is unavailable from public/admin summaries.
- Default runtime sends 0.
- Non-Rescue projects untouched.
