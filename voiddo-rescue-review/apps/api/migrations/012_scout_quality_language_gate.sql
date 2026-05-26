CREATE TABLE IF NOT EXISTS scout_self_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scout_run_id uuid NULL,
  status text NOT NULL,
  accepted_count integer NOT NULL DEFAULT 0,
  rejected_count integer NOT NULL DEFAULT 0,
  dedupe_count integer NOT NULL DEFAULT 0,
  excluded_count integer NOT NULL DEFAULT 0,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_strength_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id uuid NOT NULL,
  completeness_score integer NOT NULL DEFAULT 0,
  proof_score integer NOT NULL DEFAULT 0,
  commercial_score integer NOT NULL DEFAULT 0,
  final_score integer NOT NULL DEFAULT 0,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public_language_gate_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope text NOT NULL,
  status text NOT NULL,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scout_self_checks_run ON scout_self_checks(scout_run_id);
CREATE INDEX IF NOT EXISTS idx_audit_strength_scores_audit ON audit_strength_scores(audit_id);
