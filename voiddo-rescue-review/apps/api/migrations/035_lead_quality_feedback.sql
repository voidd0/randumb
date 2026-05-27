CREATE TABLE IF NOT EXISTS lead_quality_diagnostic_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  sampled_count integer NOT NULL DEFAULT 0,
  qualified_count integer NOT NULL DEFAULT 0,
  qualified_rate numeric(6,4) NOT NULL DEFAULT 0,
  average_final_score numeric(6,2) NOT NULL DEFAULT 0,
  blocker_count integer NOT NULL DEFAULT 0,
  summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  recommendations_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_quality_diagnostic_runs_created
  ON lead_quality_diagnostic_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS scout_source_performance_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid REFERENCES scout_sources(id) ON DELETE CASCADE,
  status text NOT NULL,
  scanned_count integer NOT NULL DEFAULT 0,
  scored_count integer NOT NULL DEFAULT 0,
  qualified_count integer NOT NULL DEFAULT 0,
  qualified_rate numeric(6,4) NOT NULL DEFAULT 0,
  average_final_score numeric(6,2) NOT NULL DEFAULT 0,
  email_coverage numeric(6,4) NOT NULL DEFAULT 0,
  issue_signal_rate numeric(6,4) NOT NULL DEFAULT 0,
  recommendation text NOT NULL,
  reasoning_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scout_source_performance_source_created
  ON scout_source_performance_scores(source_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scout_source_performance_created
  ON scout_source_performance_scores(created_at DESC);
