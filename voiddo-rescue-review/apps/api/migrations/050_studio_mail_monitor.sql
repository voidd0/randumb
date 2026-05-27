CREATE TABLE IF NOT EXISTS studio_mail_monitor_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  dry_run boolean NOT NULL DEFAULT true,
  scanned_count integer NOT NULL DEFAULT 0,
  stored_count integer NOT NULL DEFAULT 0,
  owner_command_count integer NOT NULL DEFAULT 0,
  high_priority_count integer NOT NULL DEFAULT 0,
  human_review_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_private_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS studio_mail_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mailbox text NOT NULL,
  uid text NOT NULL,
  message_id text NOT NULL,
  sender_hash text NOT NULL,
  alias text,
  classification text NOT NULL,
  priority text NOT NULL DEFAULT 'normal',
  owner_command_id uuid REFERENCES owner_commands(id) ON DELETE SET NULL,
  human_review_required boolean NOT NULL DEFAULT true,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(mailbox, uid, message_id)
);

CREATE INDEX IF NOT EXISTS idx_studio_mail_messages_class_created
  ON studio_mail_messages(classification, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_studio_mail_monitor_runs_created
  ON studio_mail_monitor_runs(created_at DESC);
