# P7 Next Self-Written TZ

Generated: 2026-05-26 17:43 IDT

## Goal

Move from self-operating foundation to autonomous lead/revenue simulation and mail clean-window recovery without enabling cold outreach.

## Tasks

1. Build lead-source simulator and approved import harness.
   - Generate 100 synthetic safe leads.
   - Run scout -> scanner jobs -> audit -> lead score -> campaign preview.

2. Build campaign economics gate.
   - Campaign preview must include expected revenue, expected cost, gross margin, and risk score.
   - Campaigns below margin/risk thresholds are blocked.

3. Build mail clean-window watcher.
   - Detect when bounce/DSN/rate-limit 24h windows clear.
   - Automatically rerun mail QA.
   - Prepare warmup next-send readiness report.
   - Do not send unless all gates pass.

4. Expand autonomous mailer.
   - Persist reply drafts for safe categories.
   - Persist alert tasks for unsafe categories.
   - Add spelling/meaning/style QA for every generated mail body.

5. Add self-learning prevention rules.
   - Every fixed bug must create a prevention rule and regression test.
   - Rules must be visible in admin.

6. Add scenario tests.
   - Synthetic lead to campaign preview.
   - Campaign economics block/pass.
   - Clean-window watcher blocks while signals exist.
   - Mailer draft creation without auto-send.

## Acceptance

- Tests increase beyond 80.
- Huanshu + 4 plugin gates pass.
- No live outreach.
- No manual warmup force.
- Review/export clean.
- Launch readiness remains honest.
