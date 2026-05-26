# Vøiddo Rescue Risk Map

Generated: 2026-05-26 06:37 IDT

## P0 Risks

1. Shared Nginx reverse proxy
   - Impact: bad config could affect all public vøiddo domains.
   - Control: add Rescue server blocks only after DNS readiness; run `nginx -t`; reload only after explicit deployment step.

2. Mailcow production mail stack
   - Impact: cold outreach mistakes could damage existing mail reputation or disrupt voiddo.com mail.
   - Control: use only `voiddorescue.com`; no voiddo.com cold outreach; no Mailcow restart; add mailboxes/domain only through controlled checklist.

3. Protected Void Factory legacy
   - Impact: owner explicitly forbids touching `/root/projects/void-factory-v2`, PM2 `voidfactory-api-3002`, `game.bruh.tools`, port `3002`, and `voidfactory` DB.
   - Control: Rescue must not inspect, restart, proxy-edit, health-check, migrate, or otherwise touch legacy assets.

4. Existing production databases
   - Impact: shared PostgreSQL and Redis host services support existing products.
   - Control: Rescue uses isolated Docker `postgres` and `redis` services with unique volumes and network.

## P1 Risks

1. Port collisions
   - Many local ports are occupied, including `3002`, `3005`, `3006-3030`, `3047`, `3049`, `3059`, `4100`, `8000`, `8003`, `8030`, `8090-8094`.
   - Control: Rescue containers should avoid random public host ports. Use Docker internal networking and Nginx proxy to named containers or fixed local ports selected after config review.

2. Existing Docker resources
   - Current Docker belongs to Mailcow.
   - Control: never run Docker prune; use unique `voiddo_rescue_*` containers, networks, and volumes.

3. Outreach compliance
   - Risk: accidental live blast, missing unsubscribe, no suppression, excessive rate.
   - Control: dry-run default; kill switch; suppression; one-click unsubscribe; per-domain/per-mailbox/global rate limits; first live launch flag required.

4. Public scan safety
   - Risk: invasive scanning could create legal/security issues.
   - Control: safe browser-only public checks; no login/admin probes; no exploit scanning; no form submissions except explicit safe dry-run mode.

## P2 Risks

1. Secrets leakage
   - Risk: env files and Mailcow API credentials exist on the host.
   - Control: never print values; never commit `.env`; reports list variable names only.

2. DNS and cert state
   - Risk: nested Rescue subdomains require new DNS and certificates.
   - Control: produce exact records first; do not edit DNS without credentials/task; configure Nginx only after records resolve.

3. Paddle setup
   - Risk: missing or wrong Paddle price IDs prevents conversion.
   - Control: require env vars and webhook tests before launch; use Paddle sandbox/live environment explicitly.

4. Autonomous fix workflow
   - Risk: customer fixes can become risky quickly.
   - Control: Level 3 changes require Codex task and review gate; plugin MVP is read-only.

## Safety Decisions Locked For MVP

- No live outreach before all safety gates pass.
- No use of existing voiddo.com mailboxes for cold outreach.
- No invasive vulnerability scanning.
- No modifications to existing projects in Phase 0.
- Rescue app state isolated under `/opt/voiddo-rescue`.
- Rescue data isolated in Docker volumes named `voiddo_rescue_*`.
