# P40 Self-Written TZ — Digest History Admin Counter

Generated: 2026-05-27 00:07 IDT

## Goal

Show the sanitized digest history count and latest-history no-send state in the protected admin Daily Digest Evidence panel.

## Tasks

1. Add `digest_agent_history` count/latest fields to the existing admin panel.
2. Keep displayed values coarse:
   - history count
   - latest history status
   - email_sent no-send
   - privacy omitted
3. Add tests:
   - admin digest endpoint includes history count
   - admin page renders history count without raw data
   - send flags remain false
4. Run Huanshu, Playwright, axe, and pa11y because this touches UI.

## Acceptance

- Protected admin shows digest history evidence.
- No raw recipients, owner personal address, message bodies, or secrets are exposed.
- Huanshu + secondary visual QA pass.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
