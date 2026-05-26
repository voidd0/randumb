from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db import execute, fetch_one
from app.main import app
from app.warmup_planner import plan_provider_spaced_warmup


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _seed_spacing_rows(token: str) -> None:
    recipients = [
        f"p11-a-{token}@gmail.com",
        f"p11-b-{token}@gmail.com",
        f"p11-c-{token}@outlook.com",
        f"p11-d-{token}@proton.me",
    ]
    for index, recipient in enumerate(recipients):
        execute(
            """
            INSERT INTO warmup_schedule(recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json)
            VALUES (%s, 'audit@voiddorescue.com', 1, now() + (%s || ' minutes')::interval, 'scheduled', %s)
            """,
            (recipient, index + 1, Jsonb({"pytest": token})),
        )


def _cleanup_spacing_rows(token: str) -> None:
    execute("DELETE FROM warmup_schedule WHERE recipient_email LIKE %s", (f"%{token}%",))


def test_provider_spacing_planner_reduces_adjacent_same_provider():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_spacing_rows(token)
        plan = plan_provider_spaced_warmup(limit=4, apply=False)
        assert plan["inspected_count"] == 4
        assert plan["current_adjacent_same_provider"] >= 1
        assert plan["proposed_adjacent_same_provider"] < plan["current_adjacent_same_provider"]
        assert plan["applied"] is False
    finally:
        _cleanup_spacing_rows(token)


def test_provider_spacing_apply_is_recorded_and_reversible_by_log():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_spacing_rows(token)
        plan = plan_provider_spaced_warmup(limit=4, apply=True)
        assert plan["status"] == "applied"
        assert plan["applied"] is True
        assert plan["proposed_json"]["policy"] == "no_send_provider_spacing_repair"
        assert all("recipient_hash" in item for item in plan["proposed_json"]["entries"])
    finally:
        _cleanup_spacing_rows(token)


def test_provider_spacing_endpoint_requires_auth_and_works():
    assert client.post("/admin/warmup/provider-spacing-plan", json={"limit": 4}).status_code == 401
    response = client.post("/admin/warmup/provider-spacing-plan", json={"limit": 4, "apply": False}, headers=admin_headers())
    assert response.status_code == 200
    assert response.json()["plan"]["applied"] is False


def test_provider_spacing_table_exists():
    row = fetch_one("SELECT to_regclass(%s) AS name", ("warmup_schedule_repairs",))
    assert row["name"] == "warmup_schedule_repairs"


def test_provider_spacing_export_does_not_store_raw_recipient_in_plan():
    token = uuid.uuid4().hex[:8]
    try:
        _seed_spacing_rows(token)
        plan = plan_provider_spaced_warmup(limit=4, apply=False)
        assert token not in str(plan["proposed_json"])
    finally:
        _cleanup_spacing_rows(token)
