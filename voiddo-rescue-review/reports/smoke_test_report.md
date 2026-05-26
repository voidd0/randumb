# Smoke Test Report

Generated: 2026-05-26 20:09 IDT

## Result

PASS

## Test Results

- API tests: `150 passed`
- smoke script: PASS, output `ok`
- API health: PASS
- web health: PASS
- Docker services: healthy

## P17 Coverage

- mailer control-room auth and blocker tests: PASS
- monitoring summary auth/no-send tests: PASS
- owner status report no-send test: PASS
- clean-window recovery no-send test: PASS

## Safety Counters

- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`
