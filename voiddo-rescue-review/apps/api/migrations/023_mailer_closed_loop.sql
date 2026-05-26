ALTER TABLE mailer_action_queue
  ADD COLUMN IF NOT EXISTS idempotency_key text NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_mailer_action_queue_idempotency
  ON mailer_action_queue(idempotency_key)
  WHERE idempotency_key <> '';

CREATE TABLE IF NOT EXISTS mailer_send_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  action_id uuid NOT NULL REFERENCES mailer_action_queue(id) ON DELETE CASCADE,
  action_type text NOT NULL,
  mailbox text NOT NULL,
  recipient_hash text NOT NULL DEFAULT '',
  template_key text NOT NULL DEFAULT '',
  status text NOT NULL,
  gate_result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mailer_send_ledger_action
  ON mailer_send_ledger(action_id);

CREATE INDEX IF NOT EXISTS idx_mailer_send_ledger_status
  ON mailer_send_ledger(status, created_at DESC);
