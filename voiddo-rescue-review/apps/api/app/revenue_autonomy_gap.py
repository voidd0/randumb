from __future__ import annotations

import math
from typing import Any

from psycopg.types.json import Jsonb

from .campaign_control_room import campaign_control_room_snapshot
from .db import execute, fetch_one
from .economics import PRODUCT_ECONOMICS, latest_economics_summary
from .p0 import json_safe
from .revenue_loop import revenue_loop_snapshot
from .self_operating import create_self_fix_task, queue_self_build, record_learning
from .source_campaign_operator import source_campaign_operator_snapshot


DEFAULT_TARGET_MRR_CENTS = 500_000
DEFAULT_APPROVED_PREVIEW_TARGET = 110
DEFAULT_PIPELINE_CONVERSION_RATE = 0.015
DEFAULT_AVG_MRR_CENTS = 4_900


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(row["count"] or 0) if row else 0


def _amount_cents(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = fetch_one(sql, params)
    return int(float(row["amount"] or 0) * 100) if row else 0


def _existing_open(table: str, where: str, params: tuple[Any, ...]) -> bool:
    return bool(fetch_one(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", params))


def _real_customer_predicate(alias: str = "c") -> str:
    return (
        f"NOT (lower({alias}.email) LIKE '%%@voiddorescue.local' "
        f"OR lower({alias}.email) LIKE '%%@example.test' "
        f"OR {alias}.paddle_customer_id LIKE 'ctm_p%%' "
        f"OR {alias}.paddle_customer_id LIKE 'ctm_onboard_%%')"
    )


def _recurring_price_floor() -> int:
    recurring = [
        int(product["price_cents"])
        for product in PRODUCT_ECONOMICS.values()
        if bool(product.get("recurring"))
    ]
    return min(recurring) if recurring else DEFAULT_AVG_MRR_CENTS


def _open_build_once(module: str, priority: str, title: str, acceptance: list[str]) -> dict[str, Any] | None:
    if _existing_open(
        "self_build_queue",
        "module = %s AND title = %s AND status = 'queued'",
        (module, title),
    ):
        return None
    return queue_self_build(module, title, priority, acceptance)


def _open_fix_once(task_type: str, priority: str, title: str, evidence: dict[str, Any]) -> dict[str, Any] | None:
    if _existing_open(
        "self_fix_tasks",
        "type = %s AND title = %s AND status = 'open'",
        (task_type, title),
    ):
        return None
    return create_self_fix_task(task_type, title, priority, evidence, "safe")


def _learn_once(signal_type: str, lesson: str, prevention_rule: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if _existing_open(
        "self_learning_events",
        "signal_type = %s AND lesson = %s AND created_at > now() - interval '14 days'",
        (signal_type, lesson),
    ):
        return None
    return record_learning(signal_type, "revenue_autonomy_gap", lesson, prevention_rule, "high", payload)


def revenue_autonomy_gap_snapshot(
    target_mrr_cents: int = DEFAULT_TARGET_MRR_CENTS,
    approved_preview_target: int = DEFAULT_APPROVED_PREVIEW_TARGET,
    assumed_conversion_rate: float = DEFAULT_PIPELINE_CONVERSION_RATE,
) -> dict[str, Any]:
    safe_target_mrr = max(100, int(target_mrr_cents or DEFAULT_TARGET_MRR_CENTS))
    safe_preview_target = max(20, int(approved_preview_target or DEFAULT_APPROVED_PREVIEW_TARGET))
    safe_conversion = max(0.001, min(float(assumed_conversion_rate or DEFAULT_PIPELINE_CONVERSION_RATE), 0.25))

    revenue = revenue_loop_snapshot(25)
    campaigns = campaign_control_room_snapshot(250, 70)
    source_operator = source_campaign_operator_snapshot(25)
    economics = latest_economics_summary()

    current_real_mrr_cents = _amount_cents(
        f"""
        SELECT COALESCE(sum(
          CASE
            WHEN lower(coalesce(s.status, '')) IN ('active', 'trialing', 'paid') THEN
              CASE product_key
                WHEN 'monitor_monthly' THEN 19
                WHEN 'fix_lite_monthly' THEN 49
                WHEN 'rescue_pro_monthly' THEN 99
                ELSE 0
              END
            ELSE 0
          END
        ), 0) AS amount
        FROM subscriptions s
        JOIN customers c ON c.id = s.customer_id
        WHERE {_real_customer_predicate('c')}
        """
    )
    real_customer_count = _count(f"SELECT count(*) FROM customers c WHERE {_real_customer_predicate('c')}")
    real_payment_count = _count(
        f"""
        SELECT count(*)
        FROM payments p
        JOIN customers c ON c.id = p.customer_id
        WHERE {_real_customer_predicate('c')}
        """
    )
    active_scout_sources = _count("SELECT count(*) FROM scout_sources WHERE status = 'active'")
    recent_scout_accepted = _count("SELECT count(*) FROM scout_leads WHERE status = 'accepted' AND created_at > now() - interval '24 hours'")
    recent_audits = _count("SELECT count(*) FROM audits WHERE created_at > now() - interval '24 hours'")

    avg_mrr_floor = _recurring_price_floor()
    customers_needed_at_floor = math.ceil(max(0, safe_target_mrr - current_real_mrr_cents) / max(1, avg_mrr_floor))
    pipeline_needed_for_target = math.ceil(customers_needed_at_floor / safe_conversion)
    effective_preview_target = max(safe_preview_target, min(10_000, pipeline_needed_for_target))
    ready_candidates = int(campaigns.get("ready_candidate_count", 0) or 0)
    active_previews = _count("SELECT count(*) FROM campaign_leads WHERE status = 'preview'")
    approved_previews = _count(
        """
        SELECT count(*)
        FROM campaign_preview_reviews r
        JOIN campaign_leads cl ON cl.id = r.campaign_lead_id
        WHERE r.action = 'approved'
          AND cl.status = 'preview'
        """
    )

    gaps: list[dict[str, Any]] = []
    if current_real_mrr_cents < safe_target_mrr:
        gaps.append(
            {
                "code": "mrr_below_target",
                "severity": "critical" if current_real_mrr_cents == 0 else "high",
                "current_mrr_cents": current_real_mrr_cents,
                "target_mrr_cents": safe_target_mrr,
                "delta_cents": safe_target_mrr - current_real_mrr_cents,
            }
        )
    if approved_previews < safe_preview_target:
        gaps.append(
            {
                "code": "approved_preview_stockpile_below_near_term_target",
                "severity": "high",
                "approved_previews": approved_previews,
                "near_term_target": safe_preview_target,
                "delta": safe_preview_target - approved_previews,
            }
        )
    if ready_candidates < min(safe_preview_target, effective_preview_target):
        gaps.append(
            {
                "code": "ready_candidate_pipeline_below_target",
                "severity": "high",
                "ready_candidates": ready_candidates,
                "target": min(safe_preview_target, effective_preview_target),
                "full_revenue_model_target": effective_preview_target,
            }
        )
    if active_scout_sources < 10:
        gaps.append(
            {
                "code": "active_scout_source_diversity_low",
                "severity": "medium",
                "active_scout_sources": active_scout_sources,
                "target": 10,
            }
        )
    if recent_scout_accepted <= 0 and ready_candidates < safe_preview_target:
        gaps.append(
            {
                "code": "recent_scout_acceptance_idle",
                "severity": "medium",
                "accepted_24h": recent_scout_accepted,
            }
        )
    if recent_audits <= 0 and ready_candidates < safe_preview_target:
        gaps.append(
            {
                "code": "recent_audit_creation_idle",
                "severity": "medium",
                "audits_24h": recent_audits,
            }
        )
    if not economics.get("all_pass"):
        gaps.append(
            {
                "code": "unit_economics_not_all_pass",
                "severity": "high",
                "economics": economics,
            }
        )

    return json_safe(
        {
            "status": "gap" if gaps else "on_track",
            "target_mrr_cents": safe_target_mrr,
            "current_real_mrr_cents": current_real_mrr_cents,
            "real_customer_count": real_customer_count,
            "real_payment_count": real_payment_count,
            "assumed_conversion_rate": safe_conversion,
            "avg_mrr_floor_cents": avg_mrr_floor,
            "customers_needed_at_floor": customers_needed_at_floor,
            "effective_preview_target": effective_preview_target,
            "near_term_approved_preview_target": safe_preview_target,
            "approved_previews": approved_previews,
            "active_previews": active_previews,
            "ready_candidates": ready_candidates,
            "active_scout_sources": active_scout_sources,
            "recent_scout_accepted_24h": recent_scout_accepted,
            "recent_audits_24h": recent_audits,
            "launch_readiness_state": revenue.get("launch_readiness_state"),
            "source_operator": {
                "candidate_count": source_operator.get("candidate_count", 0),
                "queued_or_running_runs": len(source_operator.get("queued_or_running_runs") or []),
                "scanner_jobs": source_operator.get("scanner_jobs", {}),
            },
            "gaps": gaps,
            "gap_count": len(gaps),
            "send_mail": False,
            "smtp_called": False,
            "live_outreach_allowed": False,
            "raw_recipient_addresses_included": False,
            "secrets_included": False,
        }
    )


def create_revenue_autonomy_gap_actions(
    target_mrr_cents: int = DEFAULT_TARGET_MRR_CENTS,
    approved_preview_target: int = DEFAULT_APPROVED_PREVIEW_TARGET,
    apply: bool = True,
) -> dict[str, Any]:
    snapshot = revenue_autonomy_gap_snapshot(target_mrr_cents, approved_preview_target)
    actions: list[dict[str, Any]] = []
    if not apply:
        return {**snapshot, "status": "preview_only", "actions": actions, "actions_created": 0}

    safe_evidence = {
        "snapshot": {
            key: snapshot.get(key)
            for key in [
                "target_mrr_cents",
                "current_real_mrr_cents",
                "real_customer_count",
                "approved_previews",
                "ready_candidates",
                "active_scout_sources",
                "recent_scout_accepted_24h",
                "recent_audits_24h",
                "launch_readiness_state",
            ]
        },
        "send_mail": False,
        "live_outreach_allowed": False,
        "raw_recipient_addresses_included": False,
        "secrets_included": False,
    }
    for gap in snapshot["gaps"]:
        code = str(gap["code"])
        priority = "P0" if gap.get("severity") == "critical" else "P1" if gap.get("severity") == "high" else "P2"
        title = f"Close revenue autonomy gap: {code.replace('_', ' ')}"
        if code in {"approved_preview_stockpile_below_near_term_target", "ready_candidate_pipeline_below_target"}:
            build = _open_build_once(
                "lead_supply",
                priority,
                title,
                [
                    "Run bounded lead discovery/source buildout until approved preview stockpile reaches the near-term target.",
                    "Keep cold outreach disabled and generate previews only.",
                    "Re-run campaign preflight and geo hygiene after new previews are prepared.",
                ],
            )
            if build:
                actions.append({"action": "self_build_queued", "code": code, "id": str(build["id"])})
        elif code == "active_scout_source_diversity_low":
            build = _open_build_once(
                "scout_sources",
                priority,
                title,
                [
                    "Add safe public/manual/import scout sources across at least ten niche-country segments.",
                    "Reject sensitive niches and large enterprises before scanner jobs are queued.",
                    "Record source readiness and scout self-check evidence.",
                ],
            )
            if build:
                actions.append({"action": "self_build_queued", "code": code, "id": str(build["id"])})
        elif code == "mrr_below_target":
            build = _open_build_once(
                "conversion_pipeline",
                priority,
                title,
                [
                    "Keep checkout, audit pages, previews, onboarding, and fix request creation ready for first paid conversion.",
                    "Do not enable live outreach until launch gates and owner approval pass.",
                    "Track real MRR separately from QA/test payments.",
                ],
            )
            if build:
                actions.append({"action": "self_build_queued", "code": code, "id": str(build["id"])})
        else:
            fix = _open_fix_once("revenue_autonomy_gap", priority, title, {"gap": gap, **safe_evidence})
            if fix:
                actions.append({"action": "self_fix_task_created", "code": code, "id": str(fix["id"])})

        lesson = _learn_once(
            code,
            f"Revenue gap {code.replace('_', ' ')} must generate a bounded no-send operating action.",
            f"Run revenue_autonomy_gap_agent before readiness claims and after every campaign stockpile change.",
            {"gap": gap, **safe_evidence},
        )
        if lesson:
            actions.append({"action": "learning_recorded", "code": code, "id": str(lesson["id"])})

    row = execute(
        """
        INSERT INTO self_operating_cycles(
          scope, status, findings_count, fix_tasks_created, build_items_created,
          learning_events_created, result_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            "revenue_autonomy_gap",
            "actions_created" if actions else "pass",
            int(snapshot["gap_count"]),
            len([item for item in actions if item["action"] == "self_fix_task_created"]),
            len([item for item in actions if item["action"] == "self_build_queued"]),
            len([item for item in actions if item["action"] == "learning_recorded"]),
            Jsonb({**snapshot, "actions": actions}),
        ),
    )
    return {
        **snapshot,
        "actions": actions,
        "actions_created": len(actions),
        "cycle_id": str(row["id"]),
    }
