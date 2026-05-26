from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all


PRODUCT_ECONOMICS: dict[str, dict[str, Any]] = {
    "monitor_monthly": {"price_cents": 1900, "estimated_cost_cents": 250, "recurring": True},
    "fix_lite_monthly": {"price_cents": 4900, "estimated_cost_cents": 900, "recurring": True},
    "rescue_pro_monthly": {"price_cents": 9900, "estimated_cost_cents": 1900, "recurring": True},
    "audit_onetime": {"price_cents": 4900, "estimated_cost_cents": 800, "recurring": False},
    "contact_form_repair": {"price_cents": 9900, "estimated_cost_cents": 2200, "recurring": False},
    "emergency_fix": {"price_cents": 14900, "estimated_cost_cents": 4000, "recurring": False},
}


def calculate_unit_economics(product_key: str) -> dict[str, Any]:
    product = PRODUCT_ECONOMICS.get(product_key)
    if not product:
        raise ValueError("unknown_product")
    price = int(product["price_cents"])
    cost = int(product["estimated_cost_cents"])
    margin = price - cost
    margin_percent = round((margin / price) * 100, 2) if price else 0
    decision = "pass" if margin_percent >= 70 and margin > 0 else "review"
    payback_risk = "low" if margin_percent >= 80 else "medium" if margin_percent >= 70 else "high"
    return {
        "product_key": product_key,
        "price_cents": price,
        "currency": "USD",
        "estimated_cost_cents": cost,
        "gross_margin_cents": margin,
        "gross_margin_percent": margin_percent,
        "payback_risk": payback_risk,
        "decision": decision,
        "reasoning_json": {
            "recurring": bool(product["recurring"]),
            "margin_floor_percent": 70,
            "rule": "block_or_review_if_margin_below_floor",
        },
    }


def record_economics_snapshot(product_key: str) -> dict[str, Any]:
    economics = calculate_unit_economics(product_key)
    row = execute(
        """
        INSERT INTO economics_snapshots(
          product_key, price_cents, currency, estimated_cost_cents,
          gross_margin_cents, gross_margin_percent, payback_risk, decision, reasoning_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            economics["product_key"],
            economics["price_cents"],
            economics["currency"],
            economics["estimated_cost_cents"],
            economics["gross_margin_cents"],
            economics["gross_margin_percent"],
            economics["payback_risk"],
            economics["decision"],
            Jsonb(economics["reasoning_json"]),
        ),
    )
    return dict(row)


def run_economics_audit() -> dict[str, Any]:
    snapshots = [record_economics_snapshot(product) for product in PRODUCT_ECONOMICS]
    failing = [row["product_key"] for row in snapshots if row["decision"] != "pass"]
    return {
        "status": "pass" if not failing else "review_required",
        "products": len(snapshots),
        "failing": failing,
        "snapshots": snapshots,
    }


def latest_economics_summary() -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT DISTINCT ON (product_key) product_key, price_cents, estimated_cost_cents,
          gross_margin_percent, payback_risk, decision, created_at
        FROM economics_snapshots
        ORDER BY product_key, created_at DESC
        """
    )
    return {"products": len(rows), "items": rows, "all_pass": all(row["decision"] == "pass" for row in rows)}
