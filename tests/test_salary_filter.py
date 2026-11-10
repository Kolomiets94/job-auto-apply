import main


def test_rejects_explicit_rub_salary_below_60000(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    vacancy = {"salary": {"from": 50000, "to": 55000, "currency": "RUR"}}
    assert main.salary_ok(vacancy) is False


def test_rejects_rub_salary_range_above_80000(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    vacancy = {"salary": {"from": 60000, "to": 90000, "currency": "RUR"}}
    assert main.salary_ok(vacancy) is False


def test_accepts_missing_salary(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    assert main.salary_ok({"salary": None}) is True


def test_accepts_other_currency_without_conversion(monkeypatch):
    monkeypatch.setenv("HH_MIN_SALARY_RUB", "60000")
    vacancy = {"salary": {"from": 1000, "to": 1500, "currency": "USD"}}
    assert main.salary_ok(vacancy) is True
