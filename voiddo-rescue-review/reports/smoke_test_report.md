# Smoke Test Report

Generated: 2026-05-26 22:12 IDT

## Result

PASS

## Test Results

- API tests: `207 passed`
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
- mailer action queue auth enforced: PASS
- mailer action router blocks cold outreach: PASS
- mailer action router prepares owner report without sending: PASS
- mailer action router blocks warmup outside natural timer: PASS
- mailer action summary omits raw addresses: PASS
- Paddle paid event enqueues customer onboarding action: PASS
- one-time fix purchase enqueues fix-request mail action: PASS
- customer mail action prepares without sending while gated: PASS
- customer email omitted from action queue summary: PASS
- customer mail becomes send-ready under mocked clean gates: PASS
- customer mail throttle failure blocks send-ready: PASS
- customer mail templates pass email QA: PASS
- customer mail transport dry-run does not call SMTP: PASS
- customer mail transport dry-run records sanitized result: PASS
- customer mail transport endpoint requires auth: PASS
- customer mail real-send endpoint requires auth: PASS
- customer mail real-send default gate blocks: PASS
- customer mail real-send missing flag blocks: PASS
- mocked customer SMTP send records sent: PASS
- customer SMTP failure records failed: PASS
- customer mail real-send summaries omit raw email: PASS
- customer mail idempotency dedupes: PASS
- customer mail send ledger records blocked transport: PASS
- customer mail send ledger is idempotent per action: PASS
- closed-loop executor records agent run: PASS
- closed-loop summary and endpoint omit raw recipients: PASS
- closed-loop endpoint requires auth: PASS
- recipient resolver returns customer email only inside transport boundary: PASS
- missing customer blocks transport: PASS
- suppressed customer blocks transport: PASS
- resolver audit omits raw customer email: PASS
- closed-loop default flags keep customer mail unsent: PASS
- no live outreach unlock: PASS
- no forced warmup send: PASS

## Safety Counters

- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`
