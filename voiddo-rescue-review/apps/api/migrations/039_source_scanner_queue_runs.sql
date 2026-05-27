CREATE TABLE IF NOT EXISTS source_scanner_queue_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  dry_run boolean NOT NULL DEFAULT true,
  candidate_count integer NOT NULL DEFAULT 0,
  queued_count integer NOT NULL DEFAULT 0,
  duplicate_skipped_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_source_scanner_queue_runs_created
  ON source_scanner_queue_runs(created_at DESC);
