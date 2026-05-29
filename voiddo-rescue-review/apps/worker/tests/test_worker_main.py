from __future__ import annotations

import json

from worker import main as worker_main


def test_post_send_observer_skips_without_sent_messages():
    result = worker_main.run_post_send_observer_after_outreach(0)
    assert result == {"attempted": False, "reason": "no_sent_messages"}


def test_post_send_observer_requires_admin_token(monkeypatch):
    monkeypatch.delenv("ADMIN_AUTH_TOKEN", raising=False)
    result = worker_main.run_post_send_observer_after_outreach(1)
    assert result == {"attempted": False, "reason": "admin_auth_token_missing"}


def test_post_send_observer_posts_to_protected_api(monkeypatch):
    calls: list[dict] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "ok": True,
                    "observer": {
                        "result": {
                            "decision": "CLEAN_NO_POST_SEND_BLOCKERS",
                            "pause_outreach_applied": False,
                            "blockers": [],
                        }
                    },
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        calls.append({"url": req.full_url, "headers": dict(req.header_items()), "data": req.data, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setenv("ADMIN_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("API_INTERNAL_BASE_URL", "http://api:8080")
    monkeypatch.setattr(worker_main.request, "urlopen", fake_urlopen)
    result = worker_main.run_post_send_observer_after_outreach(1)
    assert result["attempted"] is True
    assert result["ok"] is True
    assert result["decision"] == "CLEAN_NO_POST_SEND_BLOCKERS"
    assert calls[0]["url"] == "http://api:8080/admin/outreach/post-send-observer/run"
    assert calls[0]["headers"]["X-admin-token"] == "test-token"
    assert json.loads(calls[0]["data"].decode("utf-8")) == {"window_hours": 24, "apply_pause": True}


def test_observer_failure_pause_sets_runtime_control(monkeypatch):
    queries: list[tuple[str, object]] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            queries.append((sql, params))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            queries.append(("COMMIT", None))

    monkeypatch.setattr(worker_main, "connect", lambda: FakeConnection())
    result = worker_main.pause_outreach_after_observer_failure("ReadTimeout")
    assert result == {"paused": True, "reason": "ReadTimeout"}
    assert any("INSERT INTO runtime_controls" in sql for sql, _params in queries)
    assert any("outreach.post_send_observer_failed_pause" in sql for sql, _params in queries)
