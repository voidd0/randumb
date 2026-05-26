# Mailer Hardening Report

Generated: 2026-05-26 15:18 IDT

## Decision

`HARDENED_BLOCKED_BY_RECENT_SIGNALS`

Mailer throttling now blocks sends when recent delivery risk exists.

## Implemented

- `mail_signals` records bounces, DSNs, SMTP rate limits, spam/auth/TLS/DKIM/DMARC signals, inbox replies, and manual observations.
- `mail_throttle_state` stores throttle/backoff state.
- Diagnostic policy enforces spacing and duplicate prevention.
- Warmup pre-send gate blocks on recent bounce/DSN and recent SMTP rate-limit.
- Warmup skips suppressed recipients.

## Current Signals

- bounce/DSN signals, last 24h: 2
- SMTP rate-limit signals, last 24h: 1
- spam signals, last 24h: 0

## Current Decision

Warmup remains scheduled but safety-blocked until the recent signal window clears and mail QA is rerun.

## Verification

- Warmup blocked if recent bounce exists.
- Warmup blocked if recent rate-limit exists.
- Warmup skipped if recipient suppressed.
- Warmup blocked if mail QA is not PASS.
- Diagnostic cap prevents burst sends.
