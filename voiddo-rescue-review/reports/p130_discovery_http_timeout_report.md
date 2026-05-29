# P130 Discovery HTTP Timeout Report

Generated: 2026-05-29

## Change

Public lead discovery HTTP fetches now use bounded discovery timeouts:

- `DISCOVERY_HTTP_TIMEOUT_SECONDS`
- default: `12`
- clamped range: `5..25`

Applies to:

- Overpass public POI discovery.
- Apollo organization discovery when enabled.

Follow-up bounded buildout change:

- Lead supply buildout now checks the shared time budget before each heavy internal step.
- Enrichment is capped to a smaller per-step budget.
- Stockpile discovery is capped to a smaller per-step budget.
- Regional discovery is skipped unless enough time remains for its public fetch timeout.
- Scanner wait is capped to a short wait inside the overall buildout budget.
- Public contact enrichment now checks at most two pages per domain from buildout and caps each page fetch to the remaining enrichment budget.
- The daily loop now uses a snapshot-only buildout check (`apply=false`, `enrichment_limit=0`, `max_seconds=15`) so the core autonomous loop cannot be monopolized by sourcing/contact-page enrichment. Heavy buildout remains available as a separate bounded agent.

## Runtime Verification

- Focused autonomy/lead supply tests: `14 passed`, `1 skipped`.
- Focused contact/lead supply tests: `31 passed`, `1 skipped`.
- Lead discovery tests: `26 passed`.
- Bounded daily loop smoke completed with `52` agents, `0` failures, `send_mail_flags=0`, `live_flags=0`.

## Reason

A bounded lead-supply buildout call exceeded its expected outer budget because public discovery calls could wait up to 35 seconds per endpoint before scanner/buildout waits were counted. Shorter bounded HTTP timeouts keep the autonomous loop responsive and prevent a single slow provider from blocking the revenue engine.

## Safety

- No mail was sent.
- No outreach/warmup state was changed.
- No non-Rescue projects were touched.
