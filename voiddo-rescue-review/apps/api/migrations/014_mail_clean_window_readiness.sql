CREATE TABLE IF NOT EXISTS mail_clean_window_transitions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  window_hours integer NOT NULL DEFAULT 24,
  bounce_or_dsn_count integer NOT NULL DEFAULT 0,
  rate_limit_count integer NOT NULL DEFAULT 0,
  spam_signal_count integer NOT NULL DEFAULT 0,
  mail_qa_decision text NOT NULL DEFAULT 'missing',
  warmup_transition text NOT NULL DEFAULT 'not_ready',
  sends_started boolean NOT NULL DEFAULT false,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mailbox_health_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mailbox text NOT NULL,
  status text NOT NULL,
  score integer NOT NULL DEFAULT 0,
  credentials_available boolean NOT NULL DEFAULT false,
  mail_qa_decision text NOT NULL DEFAULT 'missing',
  recent_signal_count integer NOT NULL DEFAULT 0,
  throttle_allowed boolean NOT NULL DEFAULT false,
  checks_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sender_rotation_readiness (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  ready_sender_count integer NOT NULL DEFAULT 0,
  total_sender_count integer NOT NULL DEFAULT 0,
  provider_spacing_status text NOT NULL DEFAULT 'unknown',
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
