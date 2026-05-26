# Vøiddo Rescue Environment Sync - Redacted

Generated: 2026-05-26

Runtime env file:
- `/opt/voiddo-rescue/.env`
- Permissions: private runtime file, gitignored.
- Values are intentionally not recorded here.

Private source files inspected:
- `/root/.voiddo-secrets/paddle-live.env`
- `/root/.voiddo-secrets/voiddorescue-mailboxes.env`
- `/root/projects/voiddo-mailer/.env`
- `/root/scrb/backend/.env`

Synced categories:
- Paddle API key/environment/webhook secret.
- Paddle Rescue price IDs.
- SMTP/IMAP usernames and passwords for `voiddorescue.com` mailboxes.
- Lead/scoring support API variable names where available.
- Safety flags and send limits.

Variables present, values redacted:
- `COMPOSE_PROJECT_NAME=[REDACTED]`
- `POSTGRES_DB=[REDACTED]`
- `POSTGRES_USER=[REDACTED]`
- `POSTGRES_PASSWORD=[REDACTED]`
- `DATABASE_URL=[REDACTED]`
- `REDIS_URL=[REDACTED]`
- `APP_BASE_URL=[REDACTED]`
- `PRODUCT_BASE_URL=[REDACTED]`
- `API_BASE_URL=[REDACTED]`
- `AUDIT_BASE_URL=[REDACTED]`
- `GO_BASE_URL=[REDACTED]`
- `STATUS_BASE_URL=[REDACTED]`
- `STORAGE_ROOT=[REDACTED]`
- `GLOBAL_KILL_SWITCH=[REDACTED]`
- `SCANNING_PAUSED=[REDACTED]`
- `OUTREACH_DRY_RUN=[REDACTED]`
- `OUTREACH_PAUSED=[REDACTED]`
- `AUTO_REPLIES_PAUSED=[REDACTED]`
- `PADDLE_PROVISIONING_PAUSED=[REDACTED]`
- `FIRST_LIVE_SEND_FLAG=[REDACTED]`
- `INBOX_WORKER_ENABLED=[REDACTED]`
- `SMTP_HOST=[REDACTED]`
- `SMTP_PORT=[REDACTED]`
- `SMTP_USERNAME=[REDACTED]`
- `SMTP_PASSWORD=[REDACTED]`
- `SMTP_FROM_DEFAULT=[REDACTED]`
- `IMAP_HOST=[REDACTED]`
- `IMAP_PORT=[REDACTED]`
- `IMAP_USERNAME_AUDIT=[REDACTED]`
- `IMAP_PASSWORD_AUDIT=[REDACTED]`
- `IMAP_USERNAME_FIX=[REDACTED]`
- `IMAP_PASSWORD_FIX=[REDACTED]`
- `IMAP_USERNAME_SUPPORT=[REDACTED]`
- `IMAP_PASSWORD_SUPPORT=[REDACTED]`
- `MAIL_TLS_VERIFY=[REDACTED]`
- `PADDLE_API_KEY=[REDACTED]`
- `PADDLE_ENVIRONMENT=[REDACTED]`
- `PADDLE_WEBHOOK_SECRET=[REDACTED]`
- `PADDLE_PRICE_MONITOR_MONTHLY=[REDACTED]`
- `PADDLE_PRICE_FIX_LITE_MONTHLY=[REDACTED]`
- `PADDLE_PRICE_RESCUE_PRO_MONTHLY=[REDACTED]`
- `PADDLE_PRICE_AUDIT_ONETIME=[REDACTED]`
- `PADDLE_PRICE_CONTACT_FORM_REPAIR=[REDACTED]`
- `PADDLE_PRICE_EMERGENCY_FIX=[REDACTED]`
- `DAILY_SEND_LIMIT=[REDACTED]`
- `HOURLY_DOMAIN_SEND_LIMIT=[REDACTED]`
- `MAX_BOUNCE_RATE=[REDACTED]`
- `EMAIL_QA_REQUIRED=[REDACTED]`
- `VISUAL_QA_REQUIRED=[REDACTED]`
- `GEMINI_API_KEY=[REDACTED]`
- `HUNTER_API_KEY=[REDACTED]`
- `APOLLO_API_KEY=[REDACTED]`
- `PSI_KEY=[REDACTED]`
- `RESEND_API_KEY=[REDACTED]`
- `SENTRY_DSN=[REDACTED]`

Intentionally not copied into Rescue runtime:
- `MAILCOW_API_KEY`: too broad for routine app runtime; Mailcow setup script remains operator-only.
- Git credentials: deployment/operator concern, not app runtime.
- NPM token: package publishing concern, not app runtime.
