from __future__ import annotations

import os

from fastapi.testclient import TestClient

import app.main as main
from app.main import app


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_warmup_run_due_endpoint_is_admin_gated_and_no_live_outreach(monkeypatch):
    monkeypatch.setattr(
        main,
        "run_warmup_calendar_due",
        lambda limit=2: {
            "status": "idle_no_due_slots",
            "attempted": 0,
            "sent": 0,
            "blocked": 0,
            "send_mail": False,
            "live_outreach_allowed": False,
        },
    )
    assert client.post("/admin/warmup/run-due", json={"limit": 2}).status_code == 401
    response = client.post("/admin/warmup/run-due", json={"limit": 2}, headers=admin_headers())
    assert response.status_code == 200
    payload = response.json()["warmup"]
    assert payload["sent"] == 0
    assert payload["send_mail"] is False
    assert payload["live_outreach_allowed"] is False
