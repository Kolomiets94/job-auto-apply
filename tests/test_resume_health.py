from app import app
import worker


def test_resume_status_reports_configured_without_exposing_content(monkeypatch):
    secret_resume = "PRIVATE RESUME CONTENT MUST NEVER APPEAR"
    monkeypatch.setenv("RESUME", secret_resume)
    monkeypatch.delenv("RESUME_TEXT", raising=False)
    monkeypatch.setattr(worker, "load_resume_text", lambda: secret_resume)

    response = app.test_client().get("/health/resume/status")

    assert response.status_code == 200
    assert response.get_json() == {"resume_configured": True, "source": "RESUME", "resume_alias_present": True, "resume_text_present": False}
    assert secret_resume not in response.get_data(as_text=True)


def test_resume_status_reports_missing_resume(monkeypatch):
    monkeypatch.delenv("RESUME", raising=False)
    monkeypatch.delenv("RESUME_TEXT", raising=False)
    monkeypatch.delenv("RESUME_FILE", raising=False)
    monkeypatch.setattr(worker, "load_resume_text", lambda: "")

    response = app.test_client().get("/health/resume/status")

    assert response.status_code == 200
    assert response.get_json() == {"resume_configured": False, "source": "none", "resume_alias_present": False, "resume_text_present": False}
