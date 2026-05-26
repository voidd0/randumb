# Warmup Calendar Health Report

Generated: 2026-05-27 00:55 IDT

## State

- scheduled total: `28`
- warmup sent today: `0`
- warmup sent total: `0`
- live outreach sent total: `0`
- latest mail QA decision: `PASS`
- recent bounce/DSN count, last 24h: `2`
- recent SMTP rate-limit count, last 24h: `1`
- recent spam signal count, last 24h: `0`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`
- P30 admin visibility: PASS, no send unlock
- P31 mailer ops controls: PASS, no send unlock
- P32 mailer ops persistence: PASS, no send unlock
- P33 mailer ops retention: PASS, no send unlock
- P35 mailer ops digest UI: PASS, no send unlock
- P37 mailer digest runtime report: PASS, no send unlock
- P38 mailer digest admin metadata: PASS, no send unlock
- P39 mailer digest history persistence: PASS, no send unlock
- P40 mailer digest history admin counter: PASS, no send unlock
- P41 mailer digest history retention guard: PASS, no send unlock
- P42 mailer digest retention agent: PASS, no send unlock
- P43 mailer digest retention ops evidence: PASS, no send unlock
- P44 mailer digest retention admin visibility: PASS, no send unlock
- P45 mailer ops retention agent evidence: PASS, no send unlock

## P12 Schedule Gate

- provider-spacing apply status: `blocked_safety_gate`
- reason: recent mail signals
- schedule changed: `false`
- sends started: `false`

## P20 Post-Window Timer

- timer: `voiddo-rescue-post-window-recheck.timer`
- timer state: `active (waiting)`
- latest post-window status: `not_due`
- transition decision: `WAIT_UNTIL_NEXT_SAFE_AT`
- next safe timestamp: `2026-05-27T11:19:56.313413+00:00`
- sends started by post-window runner: `false`

## Next Allowed Action

No warmup send should be attempted until the recent bounce/DSN and rate-limit window clears and mail QA is rechecked. The existing systemd warmup timer remains safe because every due send is pre-gated; the P20 timer only updates no-send recovery evidence.
