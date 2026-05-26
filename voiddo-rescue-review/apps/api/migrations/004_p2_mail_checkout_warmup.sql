CREATE TABLE IF NOT EXISTS runtime_controls (
  key text PRIMARY KEY,
  value boolean NOT NULL DEFAULT false,
  source text NOT NULL DEFAULT 'system',
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runtime_controls_updated ON runtime_controls(updated_at DESC);
