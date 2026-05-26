# Smoke Test Report

Generated: 2026-05-26 20:59 IDT

## Result

PASS

## Test Results

- API tests: `172 passed`
- smoke script: PASS, output `ok`
- API health: PASS
- web health: PASS
- Docker services: healthy

## P20 Coverage

- post-window scheduler not-due before safe timestamp: PASS
- post-window scheduler due after safe timestamp: PASS
- warmup-ready transition under mocked clean window: PASS
- post-window endpoints require auth: PASS
- post-window runner writes no-send report: PASS
- post-window runner honors recovery env: PASS
- runner source has no outreach/warmup send path: PASS
- systemd timer installed and active: PASS
- mailer autonomy ledger endpoint requires auth: PASS
- mailer autonomy ledger omits raw addresses: PASS
- mailer autonomy ledger keeps live outreach blocked: PASS
- no live outreach unlock: PASS
- no forced warmup send: PASS

## Safety Counters

- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`
