CREATE TABLE IF NOT EXISTS post_scan_campaign_cycles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  dry_run boolean NOT NULL DEFAULT true,
  scanner_completed_count integer NOT NULL DEFAULT 0,
  scanner_queued_count integer NOT NULL DEFAULT 0,
  backfill_scored_count integer NOT NULL DEFAULT 0,
  backfill_qualified_count integer NOT NULL DEFAULT 0,
  source_performance_count integer NOT NULL DEFAULT 0,
  source_promote_count integer NOT NULL DEFAULT 0,
  source_pause_review_count integer NOT NULL DEFAULT 0,
  campaign_preview_count_before integer NOT NULL DEFAULT 0,
  campaign_preview_count_after integer NOT NULL DEFAULT 0,
  ready_candidate_count_after integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_post_scan_campaign_cycles_created
  ON post_scan_campaign_cycles(created_at DESC);
