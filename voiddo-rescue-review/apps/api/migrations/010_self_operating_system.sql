CREATE TABLE IF NOT EXISTS economics_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_key text NOT NULL,
  price_cents integer NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'USD',
  estimated_cost_cents integer NOT NULL DEFAULT 0,
  gross_margin_cents integer NOT NULL DEFAULT 0,
  gross_margin_percent numeric NOT NULL DEFAULT 0,
  payback_risk text NOT NULL DEFAULT 'unknown',
  decision text NOT NULL DEFAULT 'review',
  reasoning_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS self_audit_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope text NOT NULL,
  status text NOT NULL,
  score integer NOT NULL DEFAULT 0,
  findings_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS self_fix_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_audit_id uuid NULL,
  type text NOT NULL,
  priority text NOT NULL DEFAULT 'P2',
  status text NOT NULL DEFAULT 'open',
  title text NOT NULL,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  safety_level text NOT NULL DEFAULT 'safe',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS self_learning_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_type text NOT NULL,
  source text NOT NULL,
  lesson text NOT NULL,
  prevention_rule text NOT NULL,
  severity text NOT NULL DEFAULT 'info',
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS self_build_queue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module text NOT NULL,
  priority text NOT NULL DEFAULT 'P2',
  status text NOT NULL DEFAULT 'queued',
  title text NOT NULL,
  acceptance_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autonomous_mailer_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  direction text NOT NULL,
  mailbox text NOT NULL DEFAULT '',
  category text NOT NULL DEFAULT '',
  status text NOT NULL,
  action text NOT NULL,
  reason text NOT NULL,
  checks_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quality_plugin_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tool text NOT NULL,
  target text NOT NULL,
  status text NOT NULL,
  score integer NOT NULL DEFAULT 0,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  artifact_path text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_self_fix_tasks_status ON self_fix_tasks(status);
CREATE INDEX IF NOT EXISTS idx_self_build_queue_status ON self_build_queue(status);
CREATE INDEX IF NOT EXISTS idx_autonomous_mailer_decisions_created ON autonomous_mailer_decisions(created_at);
