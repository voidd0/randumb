# Launch Readiness Report

Updated: 2026-05-26 IDT

## Decision

`NOT LAUNCH READY`

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
- Go checkout endpoint fails closed with `503 checkout_not_configured` until `PADDLE_HOSTED_CHECKOUT_BASE_URL` is configured.
- Inbox persistence and idempotency implemented.
- Owner command parser, executor, and risk gates implemented.
- Huanshu local adapter is installed and visual agents pass on public/container routes.
- Mail DNS auth records are present, including DKIM.
- DMARC typo `TTL: Automatic` is not present.
- Warmup planner exists and is dry-run only.
- Lead batch importer exists and is dry-run only.
- Smoke tests pass: `26 passed`.

## Blocking Gates

- Strict SMTP TLS login fails with certificate verification error.
- Strict IMAP TLS login fails with certificate verification error.
- Deliverability test inbox pool is missing.
- Warmup recipient pool is missing.
- Paddle hosted checkout base URL is not configured.

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

Launch must remain blocked until Mailcow strict TLS, deliverability test pool, warmup recipient pool, and Paddle checkout configuration are resolved.
