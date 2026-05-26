# Vøiddo Rescue Migration Order

Applied order is filename-sorted and recorded in `schema_migrations`.

- `001_init.sql` — MVP schema.
- `002_p0_integration.sql` — P0 integration tables.
- `003_p1_launch_gate.sql` — launch gates/auth/QA.
- `004_p2_mail_checkout_warmup.sql` — mail checkout/warmup support.
- `005_p3_checkout_manifest.sql` — no-op manifest; P3 checkout was app/runtime configuration only.
- `006_p4_deliverability_warmup.sql` — deliverability and warmup pools.
- `007_warmup_calendar.sql` — scheduled warmup calendar.
- `008_p5_mail_signals.sql` — structured mail signals for bounce/rate-limit/spam/auth/TLS handling.

`005_p3_checkout_manifest.sql` may be applied after `006`/`007` on existing runtime databases because it is intentionally non-destructive and data-free.
