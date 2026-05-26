# P20 Post-Window Timer Integration Report

Generated: 2026-05-26 20:47 IDT

## Scope

P20 wired the post-window no-send recheck into Rescue automation so the system can re-evaluate mail-signal recovery after the safe timestamp without manual intervention.

## Files Added

- `apps/api/app/post_window_recheck_runner.py`
- `apps/api/tests/test_p20_post_window_runner.py`
- `scripts/run_post_window_recheck.sh`
- `scripts/systemd/voiddo-rescue-post-window-recheck.service`
- `scripts/systemd/voiddo-rescue-post-window-recheck.timer`
- `/etc/systemd/system/voiddo-rescue-post-window-recheck.service`
- `/etc/systemd/system/voiddo-rescue-post-window-recheck.timer`

## Runtime Result

- systemd timer: `voiddo-rescue-post-window-recheck.timer`
- timer status: `active (waiting)`
- latest runner status: `not_due`
- transition decision: `WAIT_UNTIL_NEXT_SAFE_AT`
- next safe timestamp: `2026-05-27T11:19:56.313413+00:00`
- sends started: `false`
- live outreach allowed: `false`

## Safety Guarantees

- The runner performs readiness evidence only.
- It does not call warmup send execution.
- It does not enable outreach flags.
- It does not send diagnostics, customer mail, or cold outreach.
- It writes a runtime report to `/app/storage/reports/post_window_recheck_runner_report.md`.

## Verification

- focused P20 tests: `5 passed`
- full API tests: `167 passed`
- smoke script: PASS, output `ok`
- Huanshu: PASS on landing, audit demo, customer, customer token dashboard, status, unsubscribe, authenticated admin
- extra QA plugins: PASS with `0` blockers

## Mailer Autonomy Note

The mailer remains autonomous but gated: recent bounce/DSN and SMTP rate-limit signals block sends for the active risk window. The timer now gives the system a recurring no-send recovery check instead of requiring manual polling.
