import main


def test_rejects_explicit_rub_salary_below_50000(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    vacancy = {"salary": {"from": 49000, "to": 49000, "currency": "RUR"}}
    assert main.salary_ok(vacancy) is False


def test_keeps_explicit_rub_salary_within_monthly_cap(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    vacancy = {"salary": {"from": 60000, "to": 70000, "currency": "RUR"}}
    assert main.salary_ok(vacancy) is True


def test_accepts_missing_salary(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    assert main.salary_ok({"salary": None}) is True


def test_accepts_other_currency_without_conversion(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    vacancy = {"salary": {"from": 1000, "to": 1500, "currency": "USD"}}
    assert main.salary_ok(vacancy) is True
