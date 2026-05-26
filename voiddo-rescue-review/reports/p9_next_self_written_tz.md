# P9 Self-Written TZ: Campaign Control + Autonomous Mailer Completion

Generated: 2026-05-26 18:12 IDT

## Goal

Turn the current import/scout/scoring foundation into a stronger campaign control room and make the autonomous mailer complete enough to operate safely once the mail clean window clears, without enabling cold outreach in this pass.

## Absolute Rules

- Do not touch non-Rescue projects.
- Do not expose secrets or raw recipient addresses.
- Do not send cold outreach.
- Do not force warmup sends manually.
- Keep `FIRST_LIVE_SEND_FLAG=false`.
- Keep `OUTREACH_PAUSED=true`.
- Keep `AUTO_REPLIES_PAUSED=true`.
- Use only `voiddorescue.com` identities for Rescue.
- Huanshu remains the canonical visual gate; axe/pa11y/pixelmatch/Lighthouse remain secondary gates.

## Tasks

1. Campaign control room
   - Add campaign readiness snapshots.
   - Show qualified leads, audit strength, expected margin, mail safety state, and blocked reasons.
   - Require every campaign preview to include audit strength and campaign economics.

2. Autonomous mailer completion
   - Add outbound decision records per message.
   - Add clear refusal reasons when gates block send.
   - Add mailbox rotation readiness without increasing Mailcow/Rspamd limits.
   - Add mailer self-check so no message can be sent without template QA, unsubscribe, suppression, throttle, mail QA, visual QA, and owner/live flags.

3. Reply handling quality
   - Add reply confidence score.
   - Add safe action plan per reply.
   - Add no-auto-reply proof when the category is angry/legal/security/custom.

4. Scout integrity
   - Add import provenance score.
   - Add rejection reason taxonomy.
   - Add duplicate-domain report for campaign preparation.

5. Tests
   - Reach at least 100 passing tests.
   - Add integration tests for campaign readiness, outbound refusal reasons, reply action plans, and scout provenance.

6. Reports and export
   - Create `reports/p9_campaign_mailer_control_report.md`.
   - Update runtime, launch, smoke, mailer, and blocker reports.
   - Create clean export `voiddo-rescue-p9-campaign-mailer-control-2026-05-26.zip`.

## Acceptance

- Campaign control room reflects real DB state.
- Every campaign preview is gated by audit strength and economics.
- Mailer can explain every no-send decision.
- Reply handling produces safe action plans.
- Tests pass.
- Huanshu and extra visual gates pass.
- Warmup sent remains unchanged unless the scheduler naturally sends after all gates pass.
- Live outreach remains `0`.
