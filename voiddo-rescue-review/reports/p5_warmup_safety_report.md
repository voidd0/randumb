# P5 Warmup Safety Report

Generated: 2026-05-26T14:21:21+03:00

Implemented:

- `mail_signals` table for bounce, DSN, SMTP rate-limit, spam, auth, TLS and inbox-reply signals.
- Warmup calendar pre-send gate before every scheduled send.
- Structural recording of diagnostic SMTP failures and inbox bounce/spam observations.
- Diagnostic policy hardening: daily cap, one diagnostic per minute, no duplicate diagnostic to already-tested inboxes.
- Owner commands: `SHOW WARMUP CALENDAR`, `SHOW MAIL SIGNALS`, `PAUSE WARMUP`, `RESUME WARMUP`.
- `RESUME WARMUP` gate checks recent bounce/DSN, rate-limit signals, latest mail QA, and pool count.
- Migration numbering fixed with no-op `005_p3_checkout_manifest.sql`; P5 mail signals added in `008_p5_mail_signals.sql`.
- Module split plan created.

Current safety state:

- approved test inboxes: 7
- approved warmup recipients: 7
- scheduled warmup messages: 28
- warmup sent: 0
- live outreach sent: 0
- bounce/DSN signals, last 24h: 2
- SMTP rate-limit signals, last 24h: 1

Result: warmup remains scheduled but is intentionally blocked until recent mail-risk signals clear and mail QA is rerun.

Verification: `python -m pytest -q` inside `voiddo_rescue_api` passed 46 tests.

Raw recipient addresses are intentionally omitted.
