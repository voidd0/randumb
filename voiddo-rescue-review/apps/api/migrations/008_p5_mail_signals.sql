CREATE TABLE IF NOT EXISTS mail_signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_type text NOT NULL,
  severity text NOT NULL DEFAULT 'info',
  source text NOT NULL DEFAULT 'system',
  mailbox text,
  recipient_hash text,
  provider text,
  message_id text,
  raw_summary text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mail_signals_type_created
  ON mail_signals(signal_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mail_signals_recipient_hash
  ON mail_signals(recipient_hash);
