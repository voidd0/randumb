from __future__ import annotations

from worker import outreach_transport


class FakeCursor:
    def __init__(self, runtime_paused: bool = False):
        self.runtime_paused = runtime_paused
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.last_sql = sql

    def fetchone(self):
        if "runtime_controls" in self.last_sql and self.runtime_paused:
            return {"exists": 1}
        return None


class FakeConnection:
    def __init__(self, runtime_paused: bool = False):
        self.runtime_paused = runtime_paused

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return FakeCursor(self.runtime_paused)

    def commit(self):
        return None


def test_outreach_queue_pause_state_blocks_on_runtime_pause(monkeypatch):
    monkeypatch.setenv("OUTREACH_DRY_RUN", "false")
    monkeypatch.setenv("OUTREACH_PAUSED", "false")
    monkeypatch.setenv("FIRST_LIVE_SEND_FLAG", "true")
    monkeypatch.setattr(outreach_transport, "connect", lambda: FakeConnection(runtime_paused=True))
    state = outreach_transport.outreach_queue_pause_state()
    assert state["paused"] is True
    assert "runtime_pause_outreach" in state["blockers"]


def test_process_outreach_queue_does_not_consume_rows_when_paused(monkeypatch):
    monkeypatch.setenv("OUTREACH_DRY_RUN", "false")
    monkeypatch.setenv("OUTREACH_PAUSED", "false")
    monkeypatch.setenv("FIRST_LIVE_SEND_FLAG", "true")
    monkeypatch.setattr(outreach_transport, "connect", lambda: FakeConnection(runtime_paused=True))
    result = outreach_transport.process_outreach_queue(1)
    assert result["processed"] == 0
    assert result["sent"] == 0
    assert result["blocked"] == 0
    assert result["paused"] is True
    assert "runtime_pause_outreach" in result["blockers"]
