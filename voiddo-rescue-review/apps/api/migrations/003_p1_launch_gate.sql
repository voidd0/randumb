CREATE TABLE IF NOT EXISTS warmup_recipients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  mailbox text NOT NULL DEFAULT 'audit@voiddorescue.com',
  source text NOT NULL DEFAULT 'owner_pool',
  status text NOT NULL DEFAULT 'approved_test_pool',
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS test_inboxes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL UNIQUE,
  provider text,
  status text NOT NULL DEFAULT 'approved',
  last_test_at timestamptz,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outreach_preview_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source text NOT NULL DEFAULT 'qualified_leads',
  status text NOT NULL DEFAULT 'dry_run_preview',
  total_candidates integer NOT NULL DEFAULT 0,
  preview_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_warmup_recipients_status ON warmup_recipients(status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_warmup_recipients_email_mailbox ON warmup_recipients(lower(email), mailbox);
CREATE INDEX IF NOT EXISTS idx_test_inboxes_status ON test_inboxes(status, created_at);
CREATE INDEX IF NOT EXISTS idx_outreach_preview_batches_created ON outreach_preview_batches(created_at DESC);
