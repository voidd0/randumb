ALTER TABLE mailer_ops_runs ADD COLUMN IF NOT EXISTS is_synthetic boolean NOT NULL DEFAULT false;
ALTER TABLE mailer_ops_runs ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'admin';

CREATE INDEX IF NOT EXISTS idx_mailer_ops_runs_synthetic_created ON mailer_ops_runs(is_synthetic, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mailer_ops_runs_source_created ON mailer_ops_runs(source, created_at DESC);

