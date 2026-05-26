# Smoke Test Report

Generated: 2026-05-26 20:34 IDT

## Result

PASS

## Test Results

- API tests: `162 passed`
- smoke script: PASS, output `ok`
- API health: PASS
- web health: PASS
- Docker services: healthy

## P19 Coverage

- post-window scheduler not-due before safe timestamp: PASS
- post-window scheduler due after safe timestamp: PASS
- warmup-ready transition under mocked clean window: PASS
- post-window endpoints require auth: PASS
- no live outreach unlock: PASS
- no forced warmup send: PASS

## Safety Counters

- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`
