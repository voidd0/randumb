# P39 Self-Written TZ — Mailer Digest Retention and Historical Evidence

Generated: 2026-05-26 23:58 IDT

## Goal

Persist a compact historical digest-agent report ledger so the autonomous system can prove daily digest runs over time without storing raw recipients, message bodies, or secrets.

## Tasks

1. Add `mailer_digest_reports` table:
   - id
   - agent_run_id
   - report_path
   - owner_report_action_id
   - email_sent
   - warmup_sent_count
   - live_outreach_sent_count
   - bounce_or_dsn_count_24h
   - rate_limit_signal_count_24h
   - blockers_json
   - created_at
2. Insert a row whenever `mailer_digest_agent` writes the runtime report.
3. Extend protected digest summary with sanitized latest/history counts.
4. Add tests:
   - row written on digest-agent run
   - history omits raw recipients/secrets
   - no-send flags remain false
   - endpoint remains auth-protected
5. No UI change unless the summary payload needs a visible history count. If UI changes, rerun Huanshu and secondary visual QA.

## Acceptance

- Digest history persists without raw recipients.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
