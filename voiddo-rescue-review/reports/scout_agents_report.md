# Scout Agents Report

Generated: 2026-05-26 15:18 IDT

## Decision

`IMPLEMENTED_DRY_RUN_READY`

Scout infrastructure now exists, but production lead sourcing is not yet connected to live external directories. Cold outreach remains disabled.

## Implemented

- `apps/api/app/scouts.py`
- `apps/worker/worker/scouts.py`
- `apps/api/app/lead_scoring.py`
- `apps/api/migrations/009_production_autonomy.sql`
- Admin-protected scout APIs:
  - `POST /admin/scouts/sources`
  - `POST /admin/scouts/runs`
  - `GET /admin/scouts/runs/{id}`
  - `POST /admin/campaigns`
  - `POST /admin/campaigns/{id}/prepare`
  - `GET /admin/campaigns/{id}`

## Supported Scout Types

- `manual_csv_scout`
- `sitemap/domain_list_scout`
- `business_directory_import_scout`
- `search_result_import_scout`
- `wordpress_footprint_scout`

## Safety

- Excluded niches are rejected before scanner jobs are queued.
- Dedupe is by normalized business domain.
- Accepted scout leads create scanner jobs only; they do not create live sends.
- No aggressive scraping or invasive website activity was added.

## Verification

- Test imports 50 lead rows and queues 50 scanner jobs.
- Duplicate domain import is deduped.
- Excluded niche import is rejected.
- Campaign preview selects qualified scored leads only.

Current runtime counters: no production scout runs have been launched yet.
