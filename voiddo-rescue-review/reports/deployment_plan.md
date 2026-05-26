# Vøiddo Rescue Deployment Plan

Generated: 2026-05-26 06:37 IDT

## Deployment Root

- Root: `/opt/voiddo-rescue`
- Reports: `/opt/voiddo-rescue/reports`
- Future source layout:
  - `/opt/voiddo-rescue/apps/web`
  - `/opt/voiddo-rescue/apps/api`
  - `/opt/voiddo-rescue/apps/worker`
  - `/opt/voiddo-rescue/apps/admin`
  - `/opt/voiddo-rescue/apps/wp-plugin`
  - `/opt/voiddo-rescue/packages/shared`
  - `/opt/voiddo-rescue/storage`
  - `/opt/voiddo-rescue/backups`
  - `/opt/voiddo-rescue/scripts`
  - `/opt/voiddo-rescue/logs`
  - `/opt/voiddo-rescue/codex_tasks`

## Docker Isolation

Use:

- `COMPOSE_PROJECT_NAME=voiddo_rescue`

Required service names:

- `voiddo_rescue_web`
- `voiddo_rescue_api`
- `voiddo_rescue_worker`
- `voiddo_rescue_postgres`
- `voiddo_rescue_redis`

Required volumes:

- `voiddo_rescue_postgres_data`
- `voiddo_rescue_redis_data`
- `voiddo_rescue_storage`

Required networks:

- `voiddo_rescue_internal`
- `voiddo_rescue_proxy`

Rules:

- No generic Docker names.
- No `docker system prune` or `docker volume prune`.
- No modification to Mailcow Compose or volumes.
- No dependency on host PostgreSQL or host Redis.
- All services need healthchecks and restart policy.
- No random public host ports; expose through Nginx after DNS/cert readiness.

## Runtime Stack

Recommended MVP stack:

- Web/app/admin: Next.js
- API: FastAPI
- Worker: Python with Playwright scanner and queue loops
- Database: PostgreSQL container
- Queue/cache: Redis container
- Browser scanner: Playwright Chromium inside worker/API image or dedicated worker image
- Mail: SMTP/IMAP abstraction pointed at `voiddorescue.com` Mailcow mailboxes after setup
- Billing: Paddle API/webhook env vars

## Public Routing Plan

Required hosts:

- `rescue.voiddo.com`
- `app.rescue.voiddo.com`
- `api.rescue.voiddo.com`
- `audit.rescue.voiddo.com`
- `go.rescue.voiddo.com`
- `status.rescue.voiddo.com`

Routing model:

- Root/product pages: `rescue.voiddo.com` -> web
- App/admin/customer dashboard: `app.rescue.voiddo.com` -> web
- API and webhooks: `api.rescue.voiddo.com` -> api
- Public audit pages: `audit.rescue.voiddo.com` -> web/api route
- Click/unsubscribe tracking: `go.rescue.voiddo.com` -> api
- Status/health page: `status.rescue.voiddo.com` -> web/status

Nginx changes are deferred until after Phase 1 app containers and Phase 2 DNS readiness. Any future Nginx edit must be preceded by a config backup and followed by `nginx -t`.

## Mail Plan

Mail domain:

- `voiddorescue.com`

Mailboxes needed:

- `hello@voiddorescue.com`
- `audit@voiddorescue.com`
- `fix@voiddorescue.com`
- `support@voiddorescue.com`
- `alerts@voiddorescue.com`
- `billing@voiddorescue.com`
- `dmarc@voiddorescue.com`
- `unsubscribe@voiddorescue.com`

No existing `voiddo.com` mailboxes are used for cold outreach.

## Required Env Vars

Rescue `.env.example` should include, with no committed values:

- `DATABASE_URL`
- `REDIS_URL`
- `APP_BASE_URL`
- `API_BASE_URL`
- `AUDIT_BASE_URL`
- `GO_BASE_URL`
- `STATUS_BASE_URL`
- `GLOBAL_KILL_SWITCH`
- `OUTREACH_DRY_RUN`
- `OUTREACH_PAUSED`
- `AUTO_REPLIES_PAUSED`
- `SCANNING_PAUSED`
- `PADDLE_PROVISIONING_PAUSED`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_DEFAULT`
- `IMAP_HOST`
- `IMAP_PORT`
- `IMAP_USERNAME_AUDIT`
- `IMAP_PASSWORD_AUDIT`
- `IMAP_USERNAME_FIX`
- `IMAP_PASSWORD_FIX`
- `IMAP_USERNAME_SUPPORT`
- `IMAP_PASSWORD_SUPPORT`
- `PADDLE_API_KEY`
- `PADDLE_ENVIRONMENT`
- `PADDLE_WEBHOOK_SECRET`
- `PADDLE_PRICE_MONITOR_MONTHLY`
- `PADDLE_PRICE_FIX_LITE_MONTHLY`
- `PADDLE_PRICE_RESCUE_PRO_MONTHLY`
- `PADDLE_PRICE_AUDIT_ONETIME`
- `PADDLE_PRICE_CONTACT_FORM_REPAIR`
- `PADDLE_PRICE_EMERGENCY_FIX`

## Phase Order

1. Complete Phase 0 inventory and reports.
2. Build isolated project foundation under `/opt/voiddo-rescue`.
3. Generate DNS and mail setup reports.
4. Implement DB schema/migrations.
5. Implement API/web/worker skeleton with healthchecks.
6. Implement safe scanner and audit-page engine.
7. Implement outreach dry-run engine, unsubscribe, suppression, and rate limits.
8. Implement Paddle checkout/webhook mock and real config hooks.
9. Implement admin/customer MVP.
10. Run smoke tests and launch-readiness gates.
11. Prepare first batch in dry-run only.
12. Require final launch flag before any live sends.

## Rollback Principle

Before public deployment, rollback should be possible by stopping/removing only `voiddo_rescue_*` containers and removing only Rescue Nginx server blocks. Existing projects, Mailcow, host PostgreSQL/Redis, and protected legacy assets remain untouched.
