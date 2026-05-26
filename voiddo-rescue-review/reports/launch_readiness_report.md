# Launch Readiness Report

Updated: 2026-05-26 12:45 IDT

## Decision

`CHECKOUT_READY_NOT_WARMED`

This is not live outreach ready.

## Passed

- Existing non-Rescue projects not modified.
- Rescue Docker services healthy.
- DB migrations applied.
- Public Rescue routes work:
  - `rescue.voiddo.com`
  - `app.rescue.voiddo.com` with admin auth gate
  - `api.rescue.voiddo.com`
  - `audit.rescue.voiddo.com`
  - `go.rescue.voiddo.com`
  - `status.rescue.voiddo.com`
- Real scanner job writes audits/issues/screenshots.
- Dynamic audit page reads API audit data.
- Dynamic admin dashboard reads DB metrics.
- Paddle webhook provisioning writes records.
- Go checkout endpoint redirects to Paddle.js client checkout page.
- Paddle client checkout page works for all six product keys.
- Inbox persistence and idempotency implemented.
- Owner command parser, executor, and risk gates implemented.
- Huanshu local adapter is installed and visual agents pass on public/container routes.
- Mail DNS auth records are present, including DKIM.
- DMARC typo `TTL: Automatic` is not present.
- Strict SMTP TLS login now passes.
- Strict IMAP TLS login now passes.
- Web admin query-token auth removed; `/admin?token=...` returns 401.
- Warmup planner exists and is dry-run only.
- Lead batch importer exists and is dry-run only.
- Smoke/P3 tests pass: `35 passed` on 2026-05-26 12:45 IDT.

## Blocking Gates

- Deliverability test inbox pool is missing.
- Warmup recipient pool is missing.

## Safety Flags

- `OUTREACH_DRY_RUN=true`
- `OUTREACH_PAUSED=true`
- `AUTO_REPLIES_PAUSED=true`
- `FIRST_LIVE_SEND_FLAG=false`
- `PADDLE_PROVISIONING_PAUSED=true`

## Live Activity

- Live outreach sent: `0`
- Warmup sent: `0`
- Customer-facing auto-replies: paused

Launch must remain blocked until deliverability test pool and warmup recipient pool are resolved and warmup has been explicitly approved.
