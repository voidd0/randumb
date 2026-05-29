# P116 Bounce-Aware Source Feedback Report

Generated: 2026-05-29 14:25 IDT

## Change

Lead quality diagnostics and scout source feedback now treat bounced/DSN-observed leads as source-quality evidence.

New behavior:

- `lead_quality_diagnostics` records `bounced_or_dsn_observed` as a low-quality reason even when the lead previously scored high.
- `scout_source_performance` records `bounced_count` and `bounce_rate`.
- Sources with enough data and bounce rate >= `20%` are marked `PAUSE_SOURCE_UNTIL_REVIEW`.
- `apply_scout_source_feedback(..., dry_run=false)` can deprioritize risky sources without sending mail.

## Runtime Evidence

- Focused tests: `23 passed`
- Lead quality status: `NEEDS_SOURCE_TUNING_NO_SEND`
- Qualified rate: `0.076`
- Source feedback status: `SOURCE_FEEDBACK_REVIEW_NO_SEND`
- Source status changes applied: `21`
- Emails sent by this pass: `0`
- Live outreach allowed: `false`

## Safety

- No cold outreach was sent.
- No warmup was forced.
- Only Rescue scout source status/config rows were changed.
- Raw recipient addresses are not included.
