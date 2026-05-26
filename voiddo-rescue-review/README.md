# Vøiddo Rescue

Autonomous, safety-gated website rescue revenue engine.

Money chain:

`lead discovery -> safe website scan -> proof audit page -> compliant outreach -> reply classification -> Paddle payment -> onboarding -> fix/monitoring workflow`

## Safety Defaults

- Outreach is paused and dry-run by default.
- Auto-replies are paused by default.
- Paddle provisioning is paused by default.
- No existing vøiddo projects, Mailcow config, shared databases, or legacy services are part of this Compose project.
- Cold outreach must use only `voiddorescue.com`.

## Local Commands

```bash
cp .env.example .env
docker compose config
docker compose up -d postgres redis api worker web
docker compose exec api python -m app.db migrate
docker compose exec api pytest -q
```

## Domains

- `rescue.voiddo.com`
- `app.rescue.voiddo.com`
- `api.rescue.voiddo.com`
- `audit.rescue.voiddo.com`
- `go.rescue.voiddo.com`
- `status.rescue.voiddo.com`

## Canonical Footer

Built by vøiddo — a small studio shipping AI-flavoured products, free dev tools, Chrome extensions and weird browser games.
