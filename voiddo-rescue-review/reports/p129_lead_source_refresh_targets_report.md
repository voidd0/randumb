# P129 Lead Source Refresh Targets Report

Generated: 2026-05-29

## Change

`quality_aware_regional_target_plan` now has a fallback when every safe target already has an Overpass scout source name:

- Keep excluding low-yield blocked segments.
- Prefer genuinely new source names when available.
- If no new safe names remain, return `ready_refresh_existing_sources` with refresh candidates.

## Reason

After bounce-aware source feedback, the lead-source loop reached `no_quality_targets` because all target names were already present. That stalled autonomous lead supply even though dedupe/scanner gates can safely handle refreshed public-source imports.

## Safety

- This does not send mail.
- It does not bypass excluded/sensitive niche filters.
- It does not weaken suppression or dedupe.
- Existing non-Rescue projects were not touched.

