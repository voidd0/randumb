CREATE TABLE IF NOT EXISTS warmup_schedule_repairs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  applied boolean NOT NULL DEFAULT false,
  inspected_count integer NOT NULL DEFAULT 0,
  current_adjacent_same_provider integer NOT NULL DEFAULT 0,
  proposed_adjacent_same_provider integer NOT NULL DEFAULT 0,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  proposed_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
