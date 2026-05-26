# P8 Next Self-Written TZ

Generated: 2026-05-26 17:56 IDT

## Goal

Move from dry-run revenue simulation to autonomous real-source lead preparation while still keeping live outreach disabled.

## Tasks

1. Build import adapters for safe real lead sources.
   - CSV import
   - domain-list import
   - directory-result import
   - no ToS-breaking scraping
   - no sensitive targets

2. Build scout self-check.
   - Each scout run must report accepted/rejected/deduped/excluded.
   - Each scout run must generate a self-audit.
   - Rejected examples must create learning events.

3. Build audit strength scoring.
   - Audit page commercial strength score.
   - Proof quality score.
   - Screenshot/evidence completeness score.

4. Build no-AI-public-language gate.
   - Scan all public pages and email templates for AI/operator/build-process wording.
   - Only studio/product language is allowed.

5. Build mail clean-window scheduler.
   - When window clears, rerun mail QA.
   - Prepare next warmup send but do not force send.
   - Record exact next allowed action.

6. Extend tests beyond 90.
   - real-source import adapter tests
   - scout self-check tests
   - audit strength score tests
   - no-AI-language gate tests
   - mail clean-window scheduler tests

## Acceptance

- tests > 90
- Huanshu + 4 plugin gates pass
- no live outreach
- no manual warmup force
- review/export clean
- launch readiness honest
