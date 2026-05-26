# Vøiddo Rescue Review Notes

- package: P51 mailer retention-history daily loop evidence
- source path: `/opt/voiddo-rescue`
- excluded: `.env`, `*.env`, mailbox passwords, private keys, storage runtime, screenshots, exports, logs, virtualenv/cache folders, `node_modules`, `.next`, `__pycache__`, `*.pyc`
- secret scan: PASS in this pass
- artifact scan: PASS in this pass
- owner personal email exposure scan: PASS in this pass
- live outreach sent: `0`
- warmup sent: `0`
- tests: targeted `35 passed`; full API `282 passed`; smoke `282 passed` + `ok`
- notes: P51 wires persisted mailer ops retention history into owner status reports, digest summary, digest agent report, and daily loop order without sending mail.
