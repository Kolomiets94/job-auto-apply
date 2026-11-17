import application_dispatcher


def test_freelance_proposals_are_never_submitted_automatically(monkeypatch):
    monkeypatch.setenv("AUTO_SEND_EMAIL", "1")
    monkeypatch.setenv("AUTO_BROWSER_APPLY", "1")
    monkeypatch.setenv("AUTO_FREELANCE_APPLY", "1")
    lead = {
        "source": "freelancehunt",
        "can_api_bid": True,
        "apply_email": "client@example.org",
        "apply_url": "https://example.org/project",
    }
    result = application_dispatcher.dispatch(lead, "Cover letter")
    assert result == {
        "status": "SKIPPED",
        "reason": "freelance_submission_not_authorized",
    }
