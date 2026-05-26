# Vøiddo Rescue Rollback Plan

Generated: 2026-05-26

Scope:
- Applies only to the isolated `/opt/voiddo-rescue` project.
- Do not run global prune commands.
- Do not touch Mailcow, existing Nginx routes, existing databases, or existing vøiddo projects.

Stop Rescue runtime:

```bash
cd /opt/voiddo-rescue
docker compose stop web api worker
```

Stop all Rescue containers:

```bash
cd /opt/voiddo-rescue
docker compose stop
```

Remove only Rescue containers and networks while preserving data volumes:

```bash
cd /opt/voiddo-rescue
docker compose down
```

Remove only Rescue volumes if a full data reset is explicitly approved:

```bash
cd /opt/voiddo-rescue
docker compose down -v
```

Disable all automation without stopping containers:

```bash
cd /opt/voiddo-rescue
perl -0pi -e 's/OUTREACH_PAUSED=.*/OUTREACH_PAUSED=true/; s/AUTO_REPLIES_PAUSED=.*/AUTO_REPLIES_PAUSED=true/; s/SCANNING_PAUSED=.*/SCANNING_PAUSED=true/; s/FIRST_LIVE_SEND_FLAG=.*/FIRST_LIVE_SEND_FLAG=false/; s/INBOX_WORKER_ENABLED=.*/INBOX_WORKER_ENABLED=false/' .env
docker compose up -d api worker web
```

Mail rollback:
- Do not delete Mailcow domain/mailboxes unless explicitly approved.
- Safe rollback is to leave `voiddorescue.com` mailboxes idle and keep Rescue sending paused.

DNS rollback:
- Remove only `voiddorescue.com` and nested `rescue.voiddo.com` records created for this project if explicitly approved.
- Do not modify top-level `voiddo.com` production mail or app records.
