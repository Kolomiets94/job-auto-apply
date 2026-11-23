import app as service


def test_live_worker_endpoint_requires_explicit_per_run_approval(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_authorized", lambda: True)
    monkeypatch.setattr(service, "run_worker", lambda: calls.append(True) or {"status": "ran"})
    client = service.app.test_client()

    denied = client.post("/run", json={})
    assert denied.status_code == 403
    assert denied.json["error"] == "explicit_live_approval_required"
    assert calls == []

    approved = client.post(
        "/run",
        json={},
        headers={"X-Hunter-Live-Approval": "APPLY"},
    )
    assert approved.status_code == 200
    assert approved.json == {"status": "ran"}
    assert calls == [True]


def test_live_worker_endpoint_still_requires_authentication(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_authorized", lambda: False)
    monkeypatch.setattr(service, "run_worker", lambda: calls.append(True))
    response = service.app.test_client().post(
        "/run",
        headers={"X-Hunter-Live-Approval": "APPLY"},
    )
    assert response.status_code == 401
    assert calls == []
