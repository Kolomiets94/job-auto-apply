import external_form_apply


def test_external_host_denied_by_default(monkeypatch):
    monkeypatch.delenv("EXTERNAL_APPLY_HOSTS", raising=False)
    assert not external_form_apply.allowed_host("https://example.org/apply")
    result = external_form_apply.apply_external({"apply_url": "https://example.org/apply"}, "Hello")
    assert result["reason"] == "external_host_not_allowlisted"


def test_external_host_requires_exact_https_allowlist(monkeypatch):
    monkeypatch.setenv("EXTERNAL_APPLY_HOSTS", "jobs.example.org")
    assert external_form_apply.allowed_host("https://jobs.example.org/apply")
    assert not external_form_apply.allowed_host("http://jobs.example.org/apply")
    assert not external_form_apply.allowed_host("https://jobs.example.org.evil.test/apply")


def test_external_browser_disabled(monkeypatch):
    monkeypatch.setenv("EXTERNAL_APPLY_HOSTS", "jobs.example.org")
    monkeypatch.delenv("AUTO_BROWSER_APPLY", raising=False)
    result = external_form_apply.apply_external({"apply_url": "https://jobs.example.org/apply"}, "Hello")
    assert result["reason"] == "browser_apply_disabled"
