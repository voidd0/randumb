CREATE TABLE IF NOT EXISTS customer_access_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz
);

CREATE TABLE IF NOT EXISTS monitoring_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  monitoring_target_id uuid NOT NULL REFERENCES monitoring_targets(id) ON DELETE CASCADE,
  scanner_job_id uuid REFERENCES scanner_jobs(id) ON DELETE SET NULL,
  status text NOT NULL,
  score integer,
  summary text,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
