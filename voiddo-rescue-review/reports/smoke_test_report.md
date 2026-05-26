# Smoke Test Report

Generated: 2026-05-26 19:55 IDT

## Result

PASS

## Test Results

- API tests: `144 passed`
- smoke script: PASS, output `ok`
- API health: PASS
- web health: PASS
- Docker services: healthy

## P16 Coverage

- monitoring scheduler tests: PASS
- customer token dashboard API tests: PASS
- sanitized customer token payload tests: PASS
- admin monitoring due endpoint auth tests: PASS

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
