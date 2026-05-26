# P18 Self-Written TZ — Clean-Window Recheck Automation + Safe Resume Moment

Generated: 2026-05-26 20:09 IDT

## Goal

Make the system automatically detect when recent bounce/DSN and rate-limit signals have aged out, rerun no-send mail QA/clean-window recovery, and expose the exact safe resume state without enabling live outreach.

## Tasks

1. Add clean-window recheck agent that records:
   - signal window clear/not clear
   - latest mail QA result
   - warmup pre-send gate result
   - exact next safe timestamp
2. Add admin/API summary for safe resume timing.
3. Add tests:
   - blocked while recent signals exist
   - ready when mocked clean signal window + mail QA PASS
   - no sends started
   - live outreach remains blocked
4. Update reports and run full QA:
   - pytest
   - smoke
   - Huanshu
   - extra visual QA plugins

## Acceptance

- At least 154 tests pass.
- No warmup send is forced manually.
- Live outreach remains `0`.
- Reports do not overstate launch readiness.
- Non-Rescue projects untouched.
