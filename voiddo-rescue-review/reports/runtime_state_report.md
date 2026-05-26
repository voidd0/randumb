# Runtime State Report

Generated: 2026-05-27 00:27 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- checkout status: `READY`
- mail auth status: `PASS`
- latest mail QA decision: `PASS`
- approved test inbox count: `7`
- approved warmup recipient count: `7`
- scheduled warmup count: `28`
- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- bounce/DSN count, last 24h: `2`
- SMTP rate-limit signal count, last 24h: `1`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Post-Window Recheck

- latest scheduler status: `not_due`
- recheck due: `false`
- transition decision: `WAIT_UNTIL_NEXT_SAFE_AT`
- next safe timestamp: `2026-05-27T11:19:56.313413+00:00`
- sends started: `false`
- live outreach allowed: `false`
- systemd timer: `voiddo-rescue-post-window-recheck.timer`
- timer state: `active (waiting)`
- timer policy: no-send readiness evidence only

## Mailer Ledger

- policy: `autonomous_mailer_all_io_gated_no_raw_addresses`
- live outreach allowed: `false`
- auto replies allowed: `false`
- owner commands tracked: `772`
- human-review inbox threads: `0`
- raw addresses included: `false`
- active blockers: `outreach_paused_env`, `first_live_send_flag_false`, `auto_replies_paused_env`, `recent_bounce_or_dsn`, `recent_rate_limit`

## Mailer Action Queue

- queued: `0`
- prepared: `0`
- blocked: `0`
- send_ready: `0`
- transport_blocked: `0`
- dry_run_recorded: `0`
- sent: `0`
- raw recipient addresses included: `false`
- send_mail: `false`
- live_outreach_allowed: `false`
- customer mail actions: onboarding, fix request, monitoring report
- customer mail sending flag: `false`
- customer mail real-send flag: `false`
- P26 real transport endpoint: implemented and protected
- P27 closed-loop executor: implemented and protected
- P28 recipient resolver boundary: implemented
- P29 customer mail simulation matrix: implemented
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- customer mail simulation cases: `126`
- customer mail simulation blocking failures: `0`
- autonomous mailer executor agent runs: `7`
- P30 admin visibility panel: implemented and protected
- P30 raw recipients in admin summaries: `false`
- P31 mailer ops action controls: implemented and protected
- P31 ops action events after cleanup: `0`
- P32 mailer ops result persistence: implemented
- P32 mailer ops run rows after cleanup: `0`
- P33 mailer ops real/synthetic retention: implemented
- P34 mailer ops daily digest hook: implemented
- P35 mailer ops digest UI surface: implemented
- P36 mailer digest scheduler agent: implemented
- P37 digest agent runtime report file: implemented
- latest digest agent report: `/opt/voiddo-rescue/reports/mailer_digest_agent_report.md`
- digest agent email_sent: `false`
- P38 digest admin report metadata: implemented and protected
- P39 digest report history table: implemented
- digest report history rows: `2`
- P40 digest history admin counter: implemented and protected
- P41 digest history retention guard: implemented and protected

## Verification

- API tests: `258 passed`
- smoke test: PASS
- Huanshu local adapter: PASS including authenticated admin digest history counter
- secondary QA plugins: Playwright/axe/pa11y PASS, 0 blockers
- API/web/worker/postgres/redis: healthy

## Next Allowed Action

Wait until `2026-05-27T11:19:56.313413+00:00`; the Rescue-only systemd timer will continue running no-send checks and transition only to warmup-ready evidence if all gates pass. Next build cycle: `P42 Digest Retention Agent`.
