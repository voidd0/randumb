CREATE TABLE IF NOT EXISTS self_operating_cycles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope text NOT NULL DEFAULT 'closed_loop',
  status text NOT NULL DEFAULT 'completed',
  findings_count integer NOT NULL DEFAULT 0,
  fix_tasks_created integer NOT NULL DEFAULT 0,
  build_items_created integer NOT NULL DEFAULT 0,
  learning_events_created integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_self_operating_cycles_created ON self_operating_cycles(created_at);
