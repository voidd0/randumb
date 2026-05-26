# Vøiddo Rescue Review Notes

- package: P50 mailer ops retention history admin surface
- source path: `/opt/voiddo-rescue`
- excluded: `.env`, `*.env`, mailbox passwords, private keys, storage runtime, screenshots, exports, logs, virtualenv/cache folders, `node_modules`, `.next`, `__pycache__`, `*.pyc`
- secret scan: PASS in this pass
- artifact scan: PASS in this pass
- owner personal email exposure scan: PASS in this pass
- live outreach sent: `0`
- warmup sent: `0`
- tests: full API `280 passed`; smoke `280 passed` + `ok`; visual QA Huanshu/Playwright/axe/pa11y PASS
- notes: P50 exposes persisted mailer ops retention report history through protected API/admin UI with no-send/no-secret/no-raw-recipient evidence.
