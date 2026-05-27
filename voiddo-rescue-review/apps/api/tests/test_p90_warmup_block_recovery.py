from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.autonomous_agents import run_agent
from app.db import execute, fetch_one
from app.main import app
from app.warmup_block_recovery import recover_blocked_warmup_slots, warmup_block_recovery_snapshot


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def _cleanup(token: str) -> None:
    execute("DELETE FROM warmup_schedule WHERE recipient_email LIKE %s OR result_json::text LIKE %s", (f"%{token}%", f"%{token}%"))
    execute("DELETE FROM system_events WHERE payload_json::text LIKE %s", (f"%{token}%",))
    execute("DELETE FROM agent_runs WHERE result_json::text LIKE %s", (f"%{token}%",))


def _blocked_slot(token: str, status: str = "blocked_recent_bounce"):
    return execute(
        """
        INSERT INTO warmup_schedule(recipient_email, sender_mailbox, day_number, scheduled_for, status, result_json)
        VALUES (%s, 'audit@voiddorescue.com', 1, now() - interval '2 hours', %s, %s)
        RETURNING *
        """,
        (f"recover-{token}@gmail.com", status, Jsonb({"token": token})),
    )


def test_warmup_block_recovery_requeues_when_gate_is_clean(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        slot = _blocked_slot(token)
        monkeypatch.setattr(
            "app.warmup_block_recovery.warmup_pre_send_gate",
            lambda row: {"allowed": True, "status": "allowed", "checks": {"token": token}},
        )
        snapshot = warmup_block_recovery_snapshot(10)
        assert snapshot["recoverable_count"] >= 1
        result = recover_blocked_warmup_slots(10, apply=True)
        assert result["recovered_count"] >= 1
        assert result["send_mail"] is False
        row = fetch_one("SELECT status, scheduled_for, result_json FROM warmup_schedule WHERE id = %s", (slot["id"],))
        assert row["status"] == "scheduled"
        assert row["scheduled_for"] > slot["scheduled_for"]
        assert row["result_json"]["warmup_block_recovery"]["send_mail"] is False
    finally:
        _cleanup(token)


def test_warmup_block_recovery_does_not_requeue_when_gate_still_blocks(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        slot = _blocked_slot(token)
        monkeypatch.setattr(
            "app.warmup_block_recovery.warmup_pre_send_gate",
            lambda row: {"allowed": False, "status": "blocked_recent_bounce", "checks": {"token": token}},
        )
        result = recover_blocked_warmup_slots(10, apply=True)
        assert result["recovered_count"] == 0
        assert result["still_blocked_count"] >= 1
        row = fetch_one("SELECT status FROM warmup_schedule WHERE id = %s", (slot["id"],))
        assert row["status"] == "blocked_recent_bounce"
    finally:
        _cleanup(token)


def test_warmup_block_recovery_endpoints_and_agent_are_no_send(monkeypatch):
    token = uuid.uuid4().hex[:8]
    try:
        _blocked_slot(token)
        monkeypatch.setattr(
            "app.warmup_block_recovery.warmup_pre_send_gate",
            lambda row: {"allowed": False, "status": "blocked_mail_qa", "checks": {"token": token}},
        )
        assert client.get("/admin/warmup/block-recovery").status_code == 401
        ok = client.get("/admin/warmup/block-recovery", headers=admin_headers())
        assert ok.status_code == 200
        assert ok.json()["recovery"]["send_mail"] is False
        assert client.post("/admin/warmup/recover-blocked", json={"apply": False}, headers=admin_headers()).status_code == 200
        agent = run_agent("warmup_block_recovery_snapshot_agent", {"limit": 10})
        assert agent["status"] == "completed"
        assert agent["result_json"]["send_mail"] is False
    finally:
        _cleanup(token)
