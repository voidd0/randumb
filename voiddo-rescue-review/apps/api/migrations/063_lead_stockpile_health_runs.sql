CREATE TABLE IF NOT EXISTS lead_stockpile_health_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL,
  decision TEXT NOT NULL,
  approved_preview_count INTEGER NOT NULL DEFAULT 0,
  target_preview_count INTEGER NOT NULL DEFAULT 50,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  source_candidate_count INTEGER NOT NULL DEFAULT 0,
  scanner_active_count INTEGER NOT NULL DEFAULT 0,
  action_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_stockpile_health_runs_created
  ON lead_stockpile_health_runs(created_at DESC);
