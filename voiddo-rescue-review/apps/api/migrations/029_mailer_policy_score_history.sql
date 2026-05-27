CREATE TABLE IF NOT EXISTS mailer_policy_score_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid,
    score integer NOT NULL DEFAULT 0,
    decision text NOT NULL,
    blocker_count integer NOT NULL DEFAULT 0,
    blockers_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    trend_guard_decision text NOT NULL DEFAULT 'unknown',
    trend_guard_regression_count integer NOT NULL DEFAULT 0,
    mail_qa_decision text NOT NULL DEFAULT 'unknown',
    bounce_or_dsn_count integer NOT NULL DEFAULT 0,
    rate_limit_count integer NOT NULL DEFAULT 0,
    spam_signal_count integer NOT NULL DEFAULT 0,
    warmup_scheduled_total integer NOT NULL DEFAULT 0,
    warmup_due_now integer NOT NULL DEFAULT 0,
    warmup_sent_today integer NOT NULL DEFAULT 0,
    warmup_blocked_today integer NOT NULL DEFAULT 0,
    mailer_action_queue_rows integer NOT NULL DEFAULT 0,
    mailer_send_ledger_rows integer NOT NULL DEFAULT 0,
    recipient_resolver_audit_rows integer NOT NULL DEFAULT 0,
    send_mail boolean NOT NULL DEFAULT false,
    smtp_called boolean NOT NULL DEFAULT false,
    live_outreach_allowed boolean NOT NULL DEFAULT false,
    raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
    secrets_included boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailer_policy_score_history_created_at
    ON mailer_policy_score_history(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mailer_policy_score_history_agent_run
    ON mailer_policy_score_history(agent_run_id);
