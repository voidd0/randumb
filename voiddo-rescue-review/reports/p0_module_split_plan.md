# P0 Module Split Plan

Status: planned; only low-risk helper extraction was done in P5.

Target split from `apps/api/app/p0.py`:

- `runtime_controls.py` — pause flags, kill switches, effective runtime state.
- `billing_events.py` — Paddle persistence and provisioning gates.
- `owner_commands.py` — owner command parsing, risk gates, execution results.
- `mail_signals.py` — recipient hashing, provider classification, bounce/rate-limit/spam/auth/TLS signals.
- `deliverability.py` — diagnostic sending, caps, provider spacing, placement signals.
- `warmup.py` — warmup pools, schedule creation, pre-send safety gate, send execution.
- `lead_batches.py` — dry-run imports and excluded-niche guards.
- `outreach_preview.py` — qualified preview queue and live-send gate.
- `audit_queries.py` — audit page/admin metrics read models.

P5 implemented the mail-signal and warmup helper logic in place to avoid a broad refactor while the runtime timer is active. The next safe refactor is to move those helpers with import-compatible wrappers and keep the existing tests unchanged.
