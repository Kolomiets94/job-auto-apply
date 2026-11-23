import sqlite3

import app as service
import queue_store


def test_deploy_one_shot_forces_draft_even_with_live_approval(monkeypatch, tmp_path):
    path = tmp_path / "one-shot.db"
    monkeypatch.setenv("HUNTER_ONE_SHOT_ID", "diagnostic-test")
    monkeypatch.setenv("AUTO_APPLY_APPROVED", "1")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(queue_store, "_db", lambda: sqlite3.connect(path))
    calls = []

    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(service.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        service,
        "run_worker",
        lambda **kwargs: calls.append(kwargs) or {"stats": {}, "results": []},
    )

    service._start_one_shot_from_deploy()

    assert calls == [{"force_dry_run": True}]
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT id FROM hunter_one_shot_runs"
        ).fetchone()
    assert row == ("diagnostic-test",)
