from __future__ import annotations

from typing import Any

from .canary_scale_plan import canary_scale_plan
from .outreach_live_queue import stage_live_outreach_batch
from .p0 import json_safe


SAFE_FLAGS = {
    "send_mail": False,
    "smtp_called": False,
    "live_outreach_allowed": False,
    "raw_recipient_addresses_included": False,
    "secrets_included": False,
}


def prepare_next_canary_batch_if_ready(canary_limit: int = 20, next_batch_limit: int = 40) -> dict[str, Any]:
    """Prepare the next outreach batch in dry-run only after the active canary is cleanly complete."""
    plan = canary_scale_plan(canary_limit, next_batch_limit, store=True)
    if plan.get("decision") != "READY_FOR_NEXT_BATCH_DRY_RUN":
        return json_safe(
            {
                "status": "not_ready",
                "decision": "NOOP_CANARY_NOT_COMPLETE",
                "scale_decision": plan.get("decision"),
                "sent_count": plan.get("sent_count", 0),
                "queued_count": plan.get("queued_count", 0),
                "blockers": plan.get("blockers", []),
                "stage": None,
                **SAFE_FLAGS,
            }
        )
    stage = stage_live_outreach_batch(
        int(plan.get("recommended_next_batch_limit") or next_batch_limit),
        dry_run=True,
        requested_by="canary_next_batch_preparer",
    )
    return json_safe(
        {
            "status": "prepared_dry_run",
            "decision": "NEXT_BATCH_DRY_RUN_PREPARED",
            "scale_decision": plan.get("decision"),
            "sent_count": plan.get("sent_count", 0),
            "queued_count": plan.get("queued_count", 0),
            "blockers": [],
            "stage": stage,
            **SAFE_FLAGS,
        }
    )
