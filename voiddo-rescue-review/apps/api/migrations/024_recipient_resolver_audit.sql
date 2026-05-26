CREATE TABLE IF NOT EXISTS recipient_resolver_audit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  action_id uuid REFERENCES mailer_action_queue(id) ON DELETE CASCADE,
  customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
  recipient_hash text NOT NULL DEFAULT '',
  status text NOT NULL,
  reason text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recipient_resolver_audit_action
  ON recipient_resolver_audit(action_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recipient_resolver_audit_status
  ON recipient_resolver_audit(status, created_at DESC);
