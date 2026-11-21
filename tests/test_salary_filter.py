import main


def test_accepts_rub_salary_below_old_implicit_floor():
    vacancy = {"salary": {"from": 40000, "to": 55000, "currency": "RUR"}}
    assert main.salary_ok(vacancy) is True


def test_collection_does_not_reject_salary_range_above_candidate_cap():
    # The collector keeps the listing; profit_ranker applies the 70k ceiling.
    vacancy = {"salary": {"from": 60000, "to": 90000, "currency": "RUR"}}
    assert main.salary_ok(vacancy) is True


def test_accepts_missing_salary():
    assert main.salary_ok({"salary": None}) is True


def test_accepts_other_currency_without_implicit_minimum():
    vacancy = {"salary": {"from": 1000, "to": 1500, "currency": "USD"}}
    assert main.salary_ok(vacancy) is True


def test_placement_still_requires_confirmed_payment():
    assert main.salary_ok({"name": "Frontend Intern", "salary": None}) is False
    assert main.salary_ok({"name": "Frontend Intern", "salary": {"from": 15000, "currency": "RUB"}}) is True
