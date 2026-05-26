# Vøiddo Rescue Smoke Test Report

Generated: 2026-05-26

## Docker

- `docker compose config --quiet`: PASS
- `docker compose up -d --build postgres redis api worker web`: PASS
- Running services:
  - `voiddo_rescue_postgres`: healthy
  - `voiddo_rescue_redis`: healthy
  - `voiddo_rescue_api`: healthy
  - `voiddo_rescue_worker`: healthy
  - `voiddo_rescue_web`: healthy

No public host ports are exposed by the Rescue compose stack.

## Database

- Migration init: PASS
- Public tables found: 15
- Tables: `businesses`, `leads`, `audits`, `audit_issues`, `screenshots`, `outreach_messages`, `email_events`, `inbox_threads`, `suppression_list`, `customers`, `payments`, `subscriptions`, `fix_requests`, `system_events`, `codex_tasks`.

## API

- `/health`: PASS
- `/api/health`: PASS
- `/admin/metrics`: PASS
- `/billing/config`: PASS
- Paddle billing config ready: PASS
- Paddle provisioning remains paused: PASS

## Web

- Next.js production build: PASS
- `web /api/health`: PASS
- Routes built: `/`, `/admin`, `/customer`, `/status`, `/r/[slug]`.
- `npm audit --omit=dev`: PASS, 0 vulnerabilities after `postcss` override.

## Worker / Scanner

- Worker healthcheck: PASS
- Public DNS from worker: PASS after attaching worker to project egress network.
- Safe scanner smoke target: `https://example.com`
- Result: completed
- Screenshots stored: 2
- Audit JSON generated: PASS
- Invasive checks: none.

## Outreach / Inbox

- Outreach preview endpoint: PASS
- Template QA on generated English preview: PASS
- Safety check blocks live sending while paused: PASS
- Suppression endpoint: PASS
- Inbox classifier `ask_price`: PASS
- Unsafe categories are configured for human review/no auto-reply.

## Visual QA

- Huashu/design-review pre-publish QA: PASS
- Desktop screenshots: PASS
- Mobile screenshots: PASS
- Automated horizontal overflow check: PASS
- Automated console error check: PASS
- API visual publish gate: PASS
- Artifacts: `/opt/voiddo-rescue/reports/visual_qa/`

## Mail

- Mailcow domain exists: PASS
- Mailboxes exist: PASS
- SMTP/IMAP diagnostic auth with TLS verification disabled: PASS
- Strict TLS SMTP/IMAP: BLOCKED by current Mailcow certificate.
- DKIM DNS: BLOCKED, record not published.
- DMARC DNS: BLOCKED, Namecheap TXT contains stray `TTL: Automatic`.

## Paddle

- Products/prices created: PASS
- Checkout config endpoint: PASS
- Webhook signature mock valid case: PASS
- Webhook invalid signature rejection: PASS

## Unit Tests

- API tests: `7 passed`
- PHP syntax for WP plugin: PASS
- Python compile pass: PASS
