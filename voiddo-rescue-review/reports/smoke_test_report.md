# Smoke Test Report

Generated: 2026-05-26 18:58 IDT

## Result

PASS

## Commands Run

- `docker compose exec -T api python -m app.db`
- `docker compose exec -T api python -m pytest -q`
- `bash scripts/run_smoke_tests.sh`
- local API health curl
- local web health curl
- Huanshu local adapter checks
- extra QA plugin checks

## Test Results

- API tests: `118 passed`
- smoke script: PASS, includes `118 passed`
- API health: PASS
- web health: PASS
- Docker services: healthy

## Visual QA Results

- Huanshu local adapter: PASS
- `axe-core-playwright`: PASS
- `pa11y`: PASS
- `pixelmatch`: PASS
- `lighthouse-ci`: PASS_WITH_WARNINGS, no blocker

## Safety Counters

- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

