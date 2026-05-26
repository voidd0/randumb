# Vøiddo Rescue Phase 0 VPS Inventory

Generated: 2026-05-26 06:37 IDT

## Host

- Hostname: `srv1240937`
- User: `root`
- Working directory at inventory time: `/root`
- Kernel: `Linux srv1240937 5.15.0-176-generic #186-Ubuntu SMP Fri Mar 13 11:01:42 UTC 2026 x86_64`
- Timezone observed from `date`: `IDT`

## Active Reverse Proxy

- Active public reverse proxy: `nginx.service`
- Public HTTP/HTTPS listeners:
  - `0.0.0.0:80`, `[::]:80` by `nginx`
  - `0.0.0.0:443`, `[::]:443` by `nginx`
- No `/etc/traefik` or `/etc/caddy` directory was present.
- Nginx enabled-site directory exists at `/etc/nginx/sites-enabled`.

## Docker

Only one Docker Compose project is running:

| Compose project | Status | Config |
| --- | --- | --- |
| `mailcowdockerized` | `running(18)` | `/opt/mailcow-dockerized/docker-compose.yml` |

Running containers are all Mailcow containers:

- `mailcowdockerized-nginx-mailcow-1`
- `mailcowdockerized-php-fpm-mailcow-1`
- `mailcowdockerized-watchdog-mailcow-1`
- `mailcowdockerized-acme-mailcow-1`
- `mailcowdockerized-ofelia-mailcow-1`
- `mailcowdockerized-rspamd-mailcow-1`
- `mailcowdockerized-dovecot-mailcow-1`
- `mailcowdockerized-postfix-mailcow-1`
- `mailcowdockerized-redis-mailcow-1`
- `mailcowdockerized-mysql-mailcow-1`
- `mailcowdockerized-postfix-tlspol-mailcow-1`
- `mailcowdockerized-clamd-mailcow-1`
- `mailcowdockerized-memcached-mailcow-1`
- `mailcowdockerized-sogo-mailcow-1`
- `mailcowdockerized-unbound-mailcow-1`
- `mailcowdockerized-dockerapi-mailcow-1`
- `mailcowdockerized-olefy-mailcow-1`
- `mailcowdockerized-netfilter-mailcow-1`

Docker networks:

- `bridge`
- `host`
- `none`
- `mailcowdockerized_mailcow-network`

Docker volumes:

- `mailcowdockerized_clamd-db-vol-1`
- `mailcowdockerized_crypt-vol-1`
- `mailcowdockerized_mysql-socket-vol-1`
- `mailcowdockerized_mysql-vol-1`
- `mailcowdockerized_postfix-tlspol-vol-1`
- `mailcowdockerized_postfix-vol-1`
- `mailcowdockerized_redis-vol-1`
- `mailcowdockerized_rspamd-vol-1`
- `mailcowdockerized_sogo-userdata-backup-vol-1`
- `mailcowdockerized_sogo-web-vol-1`
- `mailcowdockerized_vmail-index-vol-1`
- `mailcowdockerized_vmail-vol-1`
- Two anonymous local Docker volumes exist and must not be pruned.

## Mailcow

- Location: `/opt/mailcow-dockerized`
- Compose project: `mailcowdockerized`
- Status: running, 18 containers.
- Public mail listeners are Docker-published:
  - SMTP: `25`
  - Submission: `587`
  - SMTPS: `465`
  - IMAP: `143`
  - IMAPS: `993`
  - POP3/POP3S: `110`, `995`
  - Sieve: `4190`
- Mailcow web UI is bound locally through Docker:
  - `127.0.0.1:8080`
  - `127.0.0.1:8443`
- Root Nginx proxies `mail.voiddo.com` to Mailcow.
- Do not restart Mailcow or change existing voiddo.com mail flows without explicit approval.

## Occupied Ports

Important occupied ports observed by `ss -tulpn`:

- Public: `22`, `25`, `80`, `110`, `143`, `443`, `465`, `587`, `631`, `993`, `995`, `2525`, `4190`, `8001`, `8899`
- Local-only app/API ports include: `3007`, `3008`, `3009`, `3010`, `3011`, `3012`, `3013`, `3015`, `3016`, `3017`, `3018`, `3020`, `3025`, `3026`, `3028`, `3030`, `3047`, `3049`, `3059`, `3077`, `4100`, `5173`, `5180`, `5432`, `6379`, `7456`, `7654`, `8000`, `8003`, `8030`, `8080`, `8088`, `8090`, `8091`, `8093`, `8094`, `8443`, `13306`, `19991`
- Protected legacy port `3002` is active and must not be touched.
- Existing shared PostgreSQL listens on `127.0.0.1:5432`.
- Existing shared Redis listens on `127.0.0.1:6379`.

## Running System Services

Key running services include:

- Infrastructure: `nginx.service`, `docker.service`, `containerd.service`, `postgresql@14-main.service`, `redis-server.service`, `cron.service`, `pm2-root.service`, `ssh.service`
- vøiddo apps/APIs: `scrb-api`, `scrb-worker`, `scrb-ecwid`, `scrb-shopify`, `scrb-webflow`, `tells-api`, `voiddo-admin-api`, `voiddo-mailer-api`, `voiddo-mailer-worker`, `urweb-auth-api`, `urweb-pipeline`, `urweb-night-stockpile`, `urweb-webhook`, `score-voiddo`, `sitescore-api`, `setup-voiddo-api`, `rdns-helper-api`, `prompt-vault-api`, `og-meta-api`, `appeal-api`

## `/opt` Project Folders

- `/opt/android-sdk`
- `/opt/containerd`
- `/opt/crypto-alerts-v3`
- `/opt/english-quest`
- `/opt/google`
- `/opt/mailcow-dockerized`
- `/opt/rhubarb-lip-sync`
- `/opt/voiddo-rescue`

## Compose Files Under `/opt`

- `/opt/mailcow-dockerized/docker-compose.yml`

## Cron

Root crontab is populated with existing production jobs for backups, scrb, rankd, extensions pricing, voiddo-mailer, and live stats. No Rescue cron exists yet.

## Safe Deployment Path

- Safe isolated path: `/opt/voiddo-rescue`
- Safe report path created: `/opt/voiddo-rescue/reports`
- Future Docker resources must use only the `voiddo_rescue_*` names requested by the owner.
- Future public routing should be added as new Nginx server blocks for `rescue.voiddo.com` and nested Rescue subdomains only, after DNS readiness and Nginx config test.

## Immediate Risk Areas

- Nginx is shared by all public products.
- Mailcow is the only active Docker Compose project and handles live mail.
- Existing `voiddo.com` mail/domain surfaces must not be used for cold outreach.
- Protected legacy Void Factory remains active on PM2 and port `3002`; no health check or modification was performed.
- Existing root PostgreSQL/Redis are shared; Rescue should use isolated Docker PostgreSQL/Redis instead of host services.
