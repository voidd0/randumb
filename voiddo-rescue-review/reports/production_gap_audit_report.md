# Vøiddo Rescue Production Gap Audit

Generated: 2026-05-26T15:05:00+03:00

Decision: `NOT_PRODUCTION_READY`

This audit is intentionally strict. The system has a safe MVP foundation, but it is not yet a full autonomous revenue engine.

| Module | Status | Exists | Basic/stub | Missing | Risks | Required files | Acceptance |
|---|---:|---|---|---|---|---|---|
| A. lead scouting | 10% | manual lead batch dry-run | no autonomous scout workers | scout sources/runs/dedupe/scanner queue | no pipeline input | `scouts.py`, worker scouts, migrations | 50 CSV/domain leads imported, deduped, scanner jobs queued |
| B. lead enrichment | 15% | business/lead fields | no enrichment loop | source confidence, classification, normalization | weak targeting | `scouts.py`, `lead_scoring.py` | country/language/niche assigned |
| C. website scanner | 55% | scanner jobs, safe scan worker | limited checks | retry policy, stronger evidence | false positives | scanner worker/API | real audit rows and screenshots |
| D. issue scoring | 35% | audit score | deterministic/simple | sales/urgency/value/deliverability score | weak campaign priority | `lead_scoring.py` | score explanation JSON |
| E. visual audit pages | 45% | dynamic audit page | visual is MVP | stronger proof layout, language, offers | low conversion | web audit route/CSS | Huanshu + Playwright PASS |
| F. landing/product pages | 40% | landing + checkout | basic B2B copy | stronger pricing/how-it-works/trust | weak conversion | web pages/CSS | visual PASS and CTA above fold |
| G. checkout | 65% | Paddle.js/config/webhook | not end-to-end browser tested | all-product scenario matrix | checkout loss | billing/web/tests | six products scenario PASS |
| H. Paddle provisioning | 55% | payments/subscriptions/fix requests | onboarding mostly event string | onboarding_tasks, monitoring_targets | paid users under-served | p0, migrations | paid mock creates customer/payment/fix/onboarding |
| I. outreach templates | 35% | basic renderer | simple copy | template catalog, localization QA | weak replies/compliance | `email_templates.py` | EN/HE/ET render/QA PASS |
| J. mail QA | 70% | DNS/TLS/deliverability agents | placement is manual | provider-level placement | deliverability unknown | mail QA reports | strict gates remain PASS/block honest |
| K. deliverability/warmup | 70% | pools, calendar, safety gate | low-volume only | throttle table/backoff | rate-limit hit | mailer policy | no bursts possible |
| L. inbox automation | 60% | IMAP classify/persist | auto-replies paused/basic | full safe reply sender | bad replies risk | inbox worker | unsafe categories halted |
| M. owner command inbox | 65% | parser/executor/gates | limited commands | daily loop commands | over/under execution | p0/agents | safe commands execute, high-risk blocked |
| N. customer onboarding | 25% | customer dashboard shell | mock/static | onboarding_tasks, monitoring target, WP status | paid churn | web/API/migrations | mock paid customer dashboard useful |
| O. WordPress plugin | 35% | skeleton exists | not integrated | connection status, token flow | paid fix friction | wp plugin/API | read-only connection visible |
| P. fix task workflow | 45% | fix_requests, codex task creator | partial linking | auto task from paid fix | slow fulfillment | p0/agents | paid fix creates Codex task |
| Q. monitoring/reports | 45% | runtime reports | manual report updates | daily business loop | stale state | agents/reports | daily loop report PASS |
| R. visual QA agents | 55% | worker visual QA/Huanshu | shallow assertions | all route coverage | visual regressions | visual worker/tests | all public routes covered |
| S. mail QA agents | 65% | DNS/TLS agents | deliverability limited | throttle integration | rate-limit recurrence | mailer policy/mail QA | no burst tests PASS |
| T. autonomous daily loop | 15% | timer for warmup | no full loop | scout/scan/QA/report runner | idle system | `agents.py`/worker | one dry-run daily loop writes agent_runs |
| U. admin dashboard | 45% | metrics | lacks control room | scouts/campaigns/agent runs | operator blind spots | web admin/API | latest agent/scout/campaign visible |
| V. security/auth | 70% | admin token, public health/audit | customer auth weak | customer token auth | data exposure | auth/web/API | admin enforced, customer non-sensitive/tokenized |
| W. tests/scenarios | 50% | 46 tests | mostly unit/integration | full buyer journey, scouts, throttle | false readiness | tests/reports | 60+ tests including scenarios |

Immediate build path:

1. Add scout/campaign tables and code.
2. Add lead scoring engine with explainable score.
3. Add agent_runs and dry-run autonomous agents.
4. Add mail throttle policy that prevents rate-limit bursts.
5. Add onboarding_tasks and monitoring_targets.
6. Add email template catalog and QA tests.
7. Add scenario tests to pass 60+ tests.
8. Keep launch readiness honest: no live outreach until full route/visual/mail/deliverability gates pass.

Note: requested `008_scouts_campaigns.sql` cannot be used safely because `008_p5_mail_signals.sql` already exists and is applied. Production buildout uses `009_production_autonomy.sql`.

## Implementation Update

Generated: 2026-05-26T15:18:39+03:00

Implemented in this pass:

- Scout source/run/lead tables and import-based scout processing.
- Worker-side scout run processor.
- Explainable lead scoring.
- Campaign preview APIs.
- Rebuilt landing, audit, admin, customer, status, and unsubscribe visuals.
- Huanshu checks for all rebuilt pages.
- Email template catalog and QA.
- `agent_runs` and safe autonomous agent runner.
- Mail throttle/backoff state.
- Paddle checkout and webhook scenario coverage.
- Onboarding task and monitoring target tables.
- Daily loop dry-run with 7 completed agents.
- Scenario test suite expanded to 61 passing tests.

Still not production-ready:

- External lead sourcing is not connected beyond owner/import feeds.
- Recent bounce/DSN and SMTP rate-limit signals block warmup.
- External deliverability placement remains incomplete.
- Several agents are safe orchestration wrappers, not fully autonomous production workers.
- Real customer auth and WordPress connection flow need another pass.

Final decision remains `NOT_PRODUCTION_READY`; launch readiness remains `WARMUP_SCHEDULED_NO_OUTREACH`.
