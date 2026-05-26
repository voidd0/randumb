CREATE TABLE IF NOT EXISTS customer_journey_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid REFERENCES customers(id) ON DELETE CASCADE,
  status text NOT NULL,
  purchased_products_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  fix_requests_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  onboarding_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  monitoring_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
