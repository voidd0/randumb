from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_one
from .economics import calculate_unit_economics


def run_campaign_economics_check(campaign_id: str, product_key: str = "contact_form_repair", expected_conversion_rate: float = 0.02) -> dict[str, Any]:
    lead_count_row = fetch_one("SELECT count(*) AS count FROM campaign_leads WHERE campaign_id = %s", (campaign_id,))
    lead_count = int(lead_count_row["count"]) if lead_count_row else 0
    unit = calculate_unit_economics(product_key)
    expected_sales = lead_count * expected_conversion_rate
    expected_revenue = int(expected_sales * unit["price_cents"])
    expected_cost = int(expected_sales * unit["estimated_cost_cents"])
    margin = expected_revenue - expected_cost
    margin_percent = round((margin / expected_revenue) * 100, 2) if expected_revenue else 0
    risk_score = 0
    if lead_count < 20:
        risk_score += 20
    if expected_conversion_rate < 0.01:
        risk_score += 20
    if expected_sales < 1:
        risk_score += 40
    if margin_percent < 70:
        risk_score += 40
    decision = "pass" if lead_count > 0 and margin_percent >= 70 and risk_score < 50 else "blocked"
    reasoning = {
        "unit_economics": unit,
        "expected_sales": expected_sales,
        "margin_floor_percent": 70,
        "risk_floor": 50,
    }
    row = execute(
        """
        INSERT INTO campaign_economics_checks(
          campaign_id, product_key, lead_count, expected_conversion_rate, expected_revenue_cents,
          expected_cost_cents, expected_margin_percent, risk_score, decision, reasoning_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (campaign_id, product_key, lead_count, expected_conversion_rate, expected_revenue, expected_cost, margin_percent, risk_score, decision, Jsonb(reasoning)),
    )
    return dict(row)
