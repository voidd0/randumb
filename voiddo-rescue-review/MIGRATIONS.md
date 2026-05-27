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
- `009_production_autonomy.sql` through `050_studio_mail_monitor.sql` — production autonomy, mailer control room, scanner/campaign recovery, and studio mail monitor tables.
- `051_schema_migrations_manifest.sql` — non-destructive manifest for databases initialized directly from Docker SQL files.

`005_p3_checkout_manifest.sql` may be applied after `006`/`007` on existing runtime databases because it is intentionally non-destructive and data-free.

`051_schema_migrations_manifest.sql` exists because PostgreSQL Docker entrypoint applies raw SQL files without calling the app migration runner. It creates `schema_migrations` if needed and records the filename-sorted migration set without changing business data.
