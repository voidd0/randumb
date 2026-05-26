CREATE TABLE IF NOT EXISTS mailer_status_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  next_safe_action text NOT NULL,
  mail_qa_decision text,
  bounce_or_dsn_count integer NOT NULL DEFAULT 0,
  rate_limit_count integer NOT NULL DEFAULT 0,
  spam_signal_count integer NOT NULL DEFAULT 0,
  warmup_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  throttle_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  inbox_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  owner_commands_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  campaign_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  template_qa_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  quality_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mail_signal_lessons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lesson_key text NOT NULL UNIQUE,
  signal_type text NOT NULL,
  severity text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  lesson_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clean_window_recovery_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  window_hours integer NOT NULL DEFAULT 24,
  mail_qa_decision text,
  spacing_repair_id uuid REFERENCES warmup_schedule_repairs(id) ON DELETE SET NULL,
  sends_started boolean NOT NULL DEFAULT false,
  signals_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
