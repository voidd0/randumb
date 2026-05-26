CREATE TABLE IF NOT EXISTS mailer_action_queue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  action_type text NOT NULL,
  risk_level text NOT NULL DEFAULT 'SAFE_AUTO',
  status text NOT NULL DEFAULT 'queued',
  mailbox text NOT NULL DEFAULT 'audit@voiddorescue.com',
  recipient_hash text NOT NULL DEFAULT '',
  template_key text NOT NULL DEFAULT '',
  gate_result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_after timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailer_action_queue_status
  ON mailer_action_queue(status, send_after, created_at);

CREATE INDEX IF NOT EXISTS idx_mailer_action_queue_type
  ON mailer_action_queue(action_type, created_at DESC);
