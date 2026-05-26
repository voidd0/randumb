# Smoke Test Report

Generated: 2026-05-26 20:21 IDT

## Result

PASS

## Test Results

- API tests: `156 passed`
- smoke script: PASS, output `ok`
- API health: PASS
- web health: PASS
- Docker services: healthy

## P18 Coverage

- clean-window recheck blocks while recent signals exist: PASS
- clean-window recheck ready state under mocked clean window: PASS
- clean-window recheck endpoints require auth: PASS
- clean-window recheck records no-send result: PASS
- live outreach remains blocked: PASS

## Safety Counters

- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`
