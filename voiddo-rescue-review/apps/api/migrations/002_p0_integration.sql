CREATE TABLE IF NOT EXISTS scanner_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  url text NOT NULL,
  business_name text,
  dry_run boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'queued',
  priority integer NOT NULL DEFAULT 100,
  audit_id uuid REFERENCES audits(id) ON DELETE SET NULL,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error text,
  queued_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scanner_jobs_status_priority ON scanner_jobs(status, priority, queued_at);

ALTER TABLE email_events ADD COLUMN IF NOT EXISTS mailbox text;
ALTER TABLE email_events ADD COLUMN IF NOT EXISTS uid text;
ALTER TABLE email_events ADD COLUMN IF NOT EXISTS message_id text;
ALTER TABLE email_events ADD COLUMN IF NOT EXISTS classification text;
ALTER TABLE email_events ADD COLUMN IF NOT EXISTS human_review_required boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_events_inbox_idempotency
  ON email_events(mailbox, uid, message_id)
  WHERE mailbox IS NOT NULL AND uid IS NOT NULL AND message_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_email_lower ON customers(lower(email));

CREATE TABLE IF NOT EXISTS owner_commands (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mailbox text,
  uid text,
  message_id text,
  sender text NOT NULL,
  reply_to text,
  subject text,
  body text NOT NULL,
  command text NOT NULL,
  args_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  risk_level text NOT NULL,
  status text NOT NULL DEFAULT 'received',
  authentication_summary text,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  executed_at timestamptz,
  UNIQUE(mailbox, uid, message_id)
);

CREATE TABLE IF NOT EXISTS visual_qa_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent text NOT NULL,
  target_url text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  huanshu_status text NOT NULL DEFAULT 'BLOCKED_HUANSHU_NOT_AVAILABLE',
  score integer NOT NULL DEFAULT 0,
  decision text NOT NULL DEFAULT 'FAIL_BLOCK_LAUNCH',
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  screenshots_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS mail_qa_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent text NOT NULL,
  status text NOT NULL,
  decision text NOT NULL,
  checks_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warmup_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL DEFAULT 'blocked_no_recipient_pool',
  day_number integer NOT NULL DEFAULT 1,
  planned_daily_cap integer NOT NULL DEFAULT 5,
  recipient_pool_count integer NOT NULL DEFAULT 0,
  plan_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  stop_conditions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lead_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  source text NOT NULL DEFAULT 'manual',
  status text NOT NULL DEFAULT 'dry_run_imported',
  total_rows integer NOT NULL DEFAULT 0,
  accepted_rows integer NOT NULL DEFAULT 0,
  rejected_rows integer NOT NULL DEFAULT 0,
  country text,
  niche text,
  score_threshold integer NOT NULL DEFAULT 70,
  preview_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_visual_qa_runs_agent_created ON visual_qa_runs(agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mail_qa_runs_agent_created ON mail_qa_runs(agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_owner_commands_created ON owner_commands(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_batches_created ON lead_batches(created_at DESC);
