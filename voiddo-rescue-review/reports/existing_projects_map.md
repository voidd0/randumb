# Existing Projects Map

Generated: 2026-05-26 06:37 IDT

This map is read-only Phase 0 inventory. No existing project files, services, databases, containers, volumes, or proxy configs were changed.

## Protected Legacy System

- PM2 `voidfactory-api-3002`
  - Status: `online`
  - CWD: `/root/projects/void-factory-v2`
  - Exec: `/root/projects/void-factory-v2/node_modules/.bin/tsx`
  - Port observed: `3002`
  - Risk: protected legacy Telegram production. Do not touch.

## Active PM2 Apps

| Name | Status | CWD | Exec |
| --- | --- | --- | --- |
| `vf-mobile-api` | `online` | `/root/projects/vf-mobile/server` | `/root/projects/vf-mobile/server/dist/index.js` |
| `gl-api` | `online` | `/var/www/gridlock-v3/packages/server` | `/var/www/gridlock-v3/packages/server/dist/app.js` |
| `rankd-api` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/api/server.js` |
| `rankd-enrichment-worker` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/scripts/enrichment_worker.js` |
| `rankd-fresh-content` | `stopped` | `/var/www/rankd-v1` | `/var/www/rankd-v1/scripts/fresh_content_pull.js` |
| `rankd-enrich-movies` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/scripts/enrichment_worker.js` |
| `rankd-enrich-shows` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/scripts/enrichment_worker.js` |
| `rankd-enrich-music` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/scripts/enrichment_worker.js` |
| `rankd-enrich-paintings` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/scripts/enrichment_worker.js` |
| `rankd-enrich-artists` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/scripts/enrichment_worker.js` |
| `rankd-genre-enrich` | `online` | `/var/www/rankd-v1` | `/var/www/rankd-v1/api/scripts/genreEnrichWorker.js` |
| `englat-api` | `online` | `/root/projects/englat/server` | `/root/projects/englat/server/src/index.ts` |
| `curl-api` | `online` | `/root/projects/curl-api` | `/root/projects/curl-api/server.js` |
| `hackathon-api` | `online` | `/root/projects/hackathon-api` | `/usr/bin/python3` |
| `thread-writer` | `online` | `/root/projects/thread-writer` | `/usr/bin/python3` |
| `cron-voiddo-api` | `online` | `/root/projects/cron-voiddo` | `/usr/bin/python3` |
| `cron-voiddo-runner` | `online` | `/root/projects/cron-voiddo` | `/usr/bin/python3` |
| `gameui-api` | `online` | `/root/projects/gameui-api` | `/root/projects/gameui-api/server.js` |
| `quick-reply-api` | `online` | `/root/projects/quick-reply-api` | `/root/projects/quick-reply-api/server.js` |
| `deliverability-api` | `online` | `/root/projects/deliverability` | `/usr/bin/python3` |
| `email-validator-api` | `online` | `/root/projects/email-validator` | `/usr/bin/python3` |
| `audit-voiddo` | `online` | `/root/projects/audit-voiddo` | `/usr/bin/python3` |
| `mailer-saas` | `online` | `/root/projects/mailer-saas` | `/usr/bin/python3` |
| `devlog-api` | `online` | `/root/projects/devlog-api` | `/root/projects/devlog-api/server.js` |
| `devsub-monitor-3018` | `online` | `/root/projects/devsub-monitor` | `/usr/bin/python3` |

## Active Systemd Product Services

Systemd reports active vøiddo services for `appeal`, `edubridge`, `english-quest`, `og`, `open-design`, `prompt-vault`, `rdns-helper`, `score`, `scrb`, `setup`, `sitescore`, `tells`, `urweb`, `voiddo-admin`, and `voiddo-mailer`.

## Nginx Enabled Sites

Enabled site names include:

- `admin.voiddo.com`
- `appeal.voiddo.com`
- `audit.voiddo.com`
- `cron.voiddo.com`
- `curl.voiddo.com`
- `deliverability.voiddo.com`
- `devlog.voiddo.com`
- `englat.voiddo.com`
- `game.bruh.tools`
- `gameui.voiddo.com`
- `gl.voiddo.com`
- `gridlock.voiddo.com`
- `hackathon.voiddo.com`
- `hs.voiddo.com`
- `mail.voiddo.com`
- `mailcow.voiddo.com`
- `mailer.voiddo.com`
- `og.voiddo.com`
- `openclaw.voiddo.com`
- `rankd.voiddo.com`
- `rdns.voiddo.com`
- `score.voiddo.com`
- `scrb.voiddo.com.conf`
- `shim.voiddo.com`
- `tells.voiddo.com.conf`
- `urweb.voiddo.com`
- `vf-mobile`
- `voiddo.com`
- `yulia.voiddo.com`
- Legacy/non-vøiddo entries also exist for `bruh.tools`, `pnkd.dev`, `rtfm.codes`, and related buy/admin hosts.

## Static/Public Roots

Important roots observed under `/var/www`:

- `/var/www/voiddo.com`
- `/var/www/admin.voiddo.com`
- `/var/www/ai.voiddo.com`
- `/var/www/audit.voiddo.com`
- `/var/www/extensions.voiddo.com`
- `/var/www/games.voiddo.com`
- `/var/www/gridlock-v3`
- `/var/www/rankd-v1`
- `/var/www/scrb.voiddo.com`
- `/var/www/tells.voiddo.com`
- `/var/www/tools.voiddo.com`
- `/var/www/urweb.voiddo.com`
- `/var/www/vf-mobile`
- `/var/www/voidfactory`

## Source Roots

Important roots observed under `/root/projects`:

- `/root/projects/urweb-v2`
- `/root/projects/vf-mobile`
- `/root/projects/vf-reboot`
- `/root/projects/void-factory-v2` protected legacy
- `/root/projects/voiddo-mailer`
- `/root/projects/cron-voiddo`
- `/root/projects/audit-voiddo`
- `/root/projects/deliverability`
- `/root/projects/email-validator`
- `/root/projects/mailer-saas`
- `/root/projects/paddle-setup-service`
- `/root/projects/score-voiddo`
- `/root/projects/sitescore`
- `/root/projects/setup-voiddo-api`
- `/root/projects/rdns-helper`
- `/root/projects/thread-writer`
- `/root/projects/tells-wp-plugin`
- `/root/projects/rankd-wp-plugin`

## Rescue Isolation Requirement

Vøiddo Rescue must remain under `/opt/voiddo-rescue` and must not reuse existing product directories, shared app ports, shared databases, generic Docker volume names, or existing mailboxes.
