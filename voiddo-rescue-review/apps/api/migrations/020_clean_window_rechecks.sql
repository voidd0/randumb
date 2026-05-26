CREATE TABLE IF NOT EXISTS clean_window_recheck_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  window_hours integer NOT NULL DEFAULT 24,
  signal_window_clear boolean NOT NULL DEFAULT false,
  latest_mail_qa_decision text,
  next_safe_at timestamptz,
  sends_started boolean NOT NULL DEFAULT false,
  warmup_gate_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clean_window_recheck_created
  ON clean_window_recheck_runs(created_at DESC);
