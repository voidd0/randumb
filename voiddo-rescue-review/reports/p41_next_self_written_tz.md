# P41 Self-Written TZ — Mailer Digest Daily Loop Retention Guard

Generated: 2026-05-27 00:18 IDT

## Goal

Add retention guardrails for digest history so daily autonomous runs preserve useful evidence without unbounded growth or raw data exposure.

## Tasks

1. Add helper to summarize digest history retention:
   - total rows
   - rows last 24h
   - oldest retained row
   - latest no-send state
2. Add cleanup function that keeps the newest 90 digest history rows and deletes older rows.
3. Add protected no-send endpoint or agent action to run digest history cleanup.
4. Add tests:
   - cleanup keeps newest rows
   - cleanup never touches mailer action queue/send ledger
   - summaries omit raw recipients/secrets
   - no-send state remains false

## Acceptance

- Digest history has bounded retention.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
