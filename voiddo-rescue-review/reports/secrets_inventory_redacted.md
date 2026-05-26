# Secrets Inventory Redacted

Generated: 2026-05-26 06:37 IDT

Only file paths and variable names are recorded. Values were not printed.

## Env Files Found Under `/opt`

### `/opt/crypto-alerts-v3/.env`

- `BYBIT_API_KEY=[REDACTED]`
- `BYBIT_API_SECRET=[REDACTED]`
- `BYBIT_TESTNET=[REDACTED]`
- `LOG_LEVEL=[REDACTED]`
- `TELEGRAM_ADMIN_ID=[REDACTED]`
- `TELEGRAM_BOT_TOKEN=[REDACTED]`
- `TELEGRAM_CHAT_ID=[REDACTED]`
- `TG_CHANNEL_ID=[REDACTED]`
- `TG_CHAT_ID=[REDACTED]`

### `/opt/english-quest/.env`

- `APP_BASE_URL=[REDACTED]`
- `PARENT_TOKEN=[REDACTED]`
- `SMS_AYELET=[REDACTED]`
- `SMS_DAD=[REDACTED]`
- `SMS_ENABLED=[REDACTED]`
- `SMS_MIA=[REDACTED]`
- `SMS_MOM=[REDACTED]`
- `TWILIO_ACCOUNT_SID=[REDACTED]`
- `TWILIO_AUTH_TOKEN=[REDACTED]`
- `TWILIO_FROM=[REDACTED]`
- `TZ=[REDACTED]`
- `VAPID_PRIVATE_KEY=[REDACTED]`
- `VAPID_PUBLIC_KEY=[REDACTED]`
- `VAPID_SUBJECT=[REDACTED]`

## Mailcow Config Files With Secret-Like Variables

### `/opt/mailcow-dockerized/mailcow.conf`

- `ACL_ANYONE=[REDACTED]`
- `ACME_ACCOUNT_EMAIL=[REDACTED]`
- `ACME_DNS_CHALLENGE=[REDACTED]`
- `ACME_DNS_PROVIDER=[REDACTED]`
- `ADDITIONAL_SAN=[REDACTED]`
- `ADDITIONAL_SERVER_NAMES=[REDACTED]`
- `ALLOW_ADMIN_EMAIL_LOGIN=[REDACTED]`
- `API_ALLOW_FROM=[REDACTED]`
- `API_KEY=[REDACTED]`
- `AUTODISCOVER_SAN=[REDACTED]`
- `COMPOSE_PROJECT_NAME=[REDACTED]`
- `DBNAME=[REDACTED]`
- `DBPASS=[REDACTED]`
- `DBROOT=[REDACTED]`
- `DBUSER=[REDACTED]`
- `DOVECOT_MASTER_PASS=[REDACTED]`
- `DOVECOT_MASTER_USER=[REDACTED]`
- `HTTPS_BIND=[REDACTED]`
- `HTTPS_PORT=[REDACTED]`
- `HTTP_BIND=[REDACTED]`
- `HTTP_PORT=[REDACTED]`
- `IMAPS_PORT=[REDACTED]`
- `IMAP_PORT=[REDACTED]`
- `MAILCOW_HOSTNAME=[REDACTED]`
- `REDISPASS=[REDACTED]`
- `SOGO_URL_ENCRYPTION_KEY=[REDACTED]`
- `SPAMHAUS_DQS_KEY=[REDACTED]`
- `SMTP_PORT=[REDACTED]`
- `SMTPS_PORT=[REDACTED]`
- `SUBMISSION_PORT=[REDACTED]`
- other Mailcow tuning flags were present and redacted.

### `/opt/mailcow-dockerized/.env`

This file mirrors the Mailcow configuration variable set from `mailcow.conf`. Values were not printed.

## Token/Provider Reference Paths Under `/opt`

Depth-limited grep for `PADDLE|GITHUB|NPM|OPENAI|RESEND|SMTP|MAILCOW|MAIL_HOST|IMAP|DKIM|CODEX|ANTHROPIC|GEMINI` under `/opt` found references mainly in:

- `/opt/mailcow-dockerized/*`
- `/opt/mailcow-dockerized/data/conf/*`
- `/opt/mailcow-dockerized/data/web/*`
- `/opt/mailcow-dockerized/docker-compose.yml`
- `/opt/mailcow-dockerized/helper-scripts/*`
- package/vendor code under app virtualenvs
- Android SDK certificate bundle references

No Paddle, OpenAI, GitHub, NPM, Resend, Anthropic, or Gemini credential env file was found under `/opt` in this Phase 0 pass.

## Likely Existing Credential Locations Outside `/opt`

Not opened for values in Phase 0, but likely credential-bearing project roots based on active services:

- `/root/projects/urweb-v2`
- `/root/projects/voiddo-mailer`
- `/root/projects/paddle-setup-service`
- `/root/scrb`
- `/var/www/tells.voiddo.com`
- `/root/voiddo-ops`

Rescue must use its own `.env` under `/opt/voiddo-rescue` and commit only `.env.example`.
