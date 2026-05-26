# Smoke Test Report

Generated: 2026-05-27 01:13 IDT

## Result

PASS

## Test Results

- API tests: `274 passed`
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
- customer mail simulation covers all products: PASS
- customer mail simulation covers required scenarios: PASS
- customer mail simulation omits raw recipients: PASS
- customer mail simulation never calls real SMTP or live outreach: PASS
- customer mail simulation templates pass QA: PASS
- customer mail simulation endpoint requires auth: PASS
- customer mail simulation agent records no-send run: PASS
- closed-loop summary exposes resolver audit counts: PASS
- customer mail simulation summary is admin safe: PASS
- mailer visibility endpoints require auth and return counts: PASS
- visibility payloads keep sending disabled: PASS
- ops action endpoint requires auth: PASS
- customer simulation ops action is no-send: PASS
- closed-loop ops action uses dry-run transport only: PASS
- unknown ops action blocks without shell or send: PASS
- ops run row is written without send: PASS
- ops summary omits raw recipients: PASS
- unknown ops action persists as blocked: PASS
- ops summary endpoint returns persisted runs: PASS
- synthetic cleanup keeps real runs: PASS
- real ops runs remain sanitized: PASS
- summary separates real and synthetic counts: PASS
- unknown ops actions remain blocked in retention summary: PASS
- daily report includes ops run summary: PASS
- owner report draft includes ops state without raw recipients: PASS
- owner report generation sends no email: PASS
- daily digest keeps live outreach blocked: PASS
- digest summary endpoint requires auth and exposes evidence: PASS
- digest summary omits raw recipients and send flags: PASS
- digest owner-report draft stays no-send: PASS
- digest summary includes latest owner report state: PASS
- mailer digest agent exists and generates report: PASS
- mailer digest agent queues no-send owner report action: PASS
- daily loop includes mailer digest agent: PASS
- mailer digest agent records agent run evidence: PASS
- mailer digest agent writes runtime report file: PASS
- mailer digest agent runtime report omits raw recipients: PASS
- mailer digest agent runtime report confirms no-send counts: PASS
- daily loop exposes digest runtime report path: PASS
- digest summary includes runtime report metadata: PASS
- digest report metadata omits raw recipients and secrets: PASS
- digest summary endpoint returns report metadata behind auth: PASS
- digest summary send flags remain false with runtime report: PASS
- digest history row written on agent run: PASS
- digest history omits raw recipients and secrets: PASS
- digest summary includes sanitized history: PASS
- admin digest history counter visible: PASS
- digest history cleanup keeps newest rows: PASS
- digest history cleanup preserves action queue and send ledger: PASS
- digest history retention summary omits raw recipients and secrets: PASS
- digest history cleanup endpoint requires auth and remains no-send: PASS
- mailer digest retention agent exists: PASS
- mailer digest retention agent deletes old digest rows: PASS
- daily loop includes mailer digest retention agent: PASS
- mailer digest retention agent leaves send flags false: PASS
- digest history cleanup ops action runs and persists: PASS
- digest history cleanup ops action is sanitized no-send: PASS
- digest history cleanup ops action preserves action queue/send ledger: PASS
- digest history cleanup ops endpoint is no-send and persisted: PASS
- admin digest cleanup button source assertion: PASS
- admin digest cleanup latest-list visual assertion: PASS
- mailer ops retention agent exists and remains no-send: PASS
- mailer ops retention agent deletes synthetic rows only: PASS
- mailer ops retention helper reports counts without send: PASS
- daily loop includes mailer ops retention agent: PASS
- mailer ops summary exposes retention agent evidence without send: PASS
- admin retention summary source assertion: PASS
- admin retention summary visual assertion: PASS
- mailer ops retention agent writes runtime report file: PASS
- mailer ops retention agent report omits raw recipients and secrets: PASS
- daily loop exposes mailer ops retention report metadata: PASS
- no live outreach unlock: PASS
- no forced warmup send: PASS

## Safety Counters

- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`
- customer mail real SMTP sent count: `0`
- mailer action queue after cleanup: `0`
- mailer send ledger after cleanup: `0`
- recipient resolver audit after cleanup: `0`
- ops action events after cleanup: retained no-send admin evidence only
- mailer ops run rows retained: `1`
- mailer ops synthetic rows retained: `0`
- latest retained ops action: `digest_history_cleanup:completed:send=false`
- latest retained ops agent: `completed:0:1:send=false`
- latest retained ops report: `/app/storage/reports/mailer_ops_retention_agent_report.md`
- digest report history rows retained: `2`
