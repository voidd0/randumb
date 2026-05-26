# Warmup Readiness Report

Updated: 2026-05-26 14:02 IDT

## Status

Warmup is implemented as an autonomous low-volume calendar. It is scheduled but has not sent yet.

Current blockers:

- Owner-approved warmup recipient pool exists.
- Owner-approved deliverability test inbox pool exists.
- Warmup calendar exists with daily cap `2`.
- Systemd timer `voiddo-rescue-warmup-calendar.timer` is active and checks due sends every 15 minutes.
- Latest diagnostic history includes rate-limit/bounce signal, so the calendar starts after cooldown instead of sending immediately.

## Implemented

- `WARMUP_RECIPIENT_POOL` runtime config support.
- Protected import endpoint: `POST /warmup/recipients/import`.
- Import validation rejects invalid, duplicate, and suppressed addresses.
- Approved recipients are stored with `source=owner_provided`.
- Dry-run warmup schedule preview.
- Owner command `PREPARE WARMUP` uses the real approved env+DB pool count.
- Owner command `START WARMUP DAY=1` now has a real send executor, but only after all gates pass.
- Autonomous calendar table: `warmup_schedule`.
- Autonomous runner: `/opt/voiddo-rescue/scripts/run_warmup_calendar.sh`.
- Host timer: `voiddo-rescue-warmup-calendar.timer`.
- Sender rotation: `audit@`, `support@`, `fix@` on `voiddorescue.com`.

## Day Caps

- Calendar mode: `2/day`.
- Slot 1: `10:15 Asia/Jerusalem`.
- Slot 2: `16:15 Asia/Jerusalem`.
- Current plan length: `14 days`, `28 scheduled messages`.
- Recipient ordering prefers owner/Gmail controls first, then external controls, then internal controls.

## Day 1 Send Gate

Required before any warmup send:

- approved warmup recipient pool exists
- mail QA decision is `PASS`
- deliverability diagnostics have no blocking failure
- authenticated owner command approves `START WARMUP DAY=1`
- daily cap enforced at `5`

Current result:

- Warmup recipient pool count: `0`
- Warmup recipient pool count after import: `7`
- Runtime warmup import accepted: `7`
- Runtime warmup import rejected: `0`
- Warmup scheduled messages: `28`
- Warmup day 1 sent: `0`
- Warmup status: `scheduled_autonomous_calendar`
- Bounce count after inbox poll: `2`
- Typo address disabled and corrected Gmail imported into warmup pool.

## Stop Conditions

- bounce
- spam signal
- auth failure
- TLS failure
- DKIM failure
- DMARC failure

## Decision

`WARMUP_SCHEDULED_NO_OUTREACH`

## P5 Safety Gate

Updated: 2026-05-26 14:21 IDT

Every scheduled warmup send now checks `pause_warmup`, global worker pause, latest mail QA, recent bounce/DSN count, recent SMTP rate-limit count, suppression, sender credentials and the daily cap immediately before SMTP.

Current structural mail signals:

- bounce/DSN, last 24h: `2`
- SMTP rate-limit, last 24h: `1`
- spam signal, last 24h: `0`

Because bounce/DSN and rate-limit counts are non-zero, the calendar is safety-blocked until the 24-hour window clears and mail QA is rerun. Warmup sent remains `0`.
