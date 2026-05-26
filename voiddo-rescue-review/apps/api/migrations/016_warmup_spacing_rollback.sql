CREATE TABLE IF NOT EXISTS warmup_schedule_rollbacks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  repair_id uuid REFERENCES warmup_schedule_repairs(id) ON DELETE SET NULL,
  status text NOT NULL,
  restored_count integer NOT NULL DEFAULT 0,
  skipped_count integer NOT NULL DEFAULT 0,
  rollback_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
