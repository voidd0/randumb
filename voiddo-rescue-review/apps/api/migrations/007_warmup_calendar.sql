CREATE TABLE IF NOT EXISTS warmup_schedule (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_email text NOT NULL,
  sender_mailbox text NOT NULL DEFAULT 'audit@voiddorescue.com',
  day_number integer NOT NULL DEFAULT 1,
  scheduled_for timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'scheduled',
  sent_at timestamptz,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_warmup_schedule_due ON warmup_schedule(status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_warmup_schedule_recipient ON warmup_schedule(lower(recipient_email), status);
