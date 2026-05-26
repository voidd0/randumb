CREATE TABLE IF NOT EXISTS post_window_recheck_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  window_hours integer NOT NULL DEFAULT 24,
  next_safe_at timestamptz,
  recheck_due boolean NOT NULL DEFAULT false,
  recheck_executed_at timestamptz,
  transition_decision text NOT NULL,
  sends_started boolean NOT NULL DEFAULT false,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_post_window_recheck_created
  ON post_window_recheck_runs(created_at DESC);
