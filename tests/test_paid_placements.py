import unittest
from entry_level import is_entry_level, placement_is_paid
from profit_ranker import rank_lead


class PaidPlacementTests(unittest.TestCase):
    def test_paid_frontend_titles_are_eligible_and_routed(self):
        for title in ("Frontend Intern", "Стажёр React", "Практикант HTML CSS", "Стажировка верстальщик"):
            with self.subTest(title=title):
                lead = rank_lead({"source": "hh", "title": title, "location": "Россия",
                                  "salary": {"from": 30000, "currency": "RUB"}})
                self.assertTrue(lead["eligible"], lead.get("rank_reason"))
                self.assertEqual(lead["opportunity_type"], "paid_placement")
    def test_missing_salary_is_manual_review_but_unpaid_and_zero_are_rejected(self):
        unknown = rank_lead({"source": "hh", "title": "React Intern", "description": "React"})
        self.assertTrue(unknown["eligible"])
        self.assertTrue(unknown["salary_review_required"])
        for description, salary in (("Unpaid React internship", {"from": 30000, "currency": "RUB"}),
                                    ("Неоплачиваемая практика React", None),
                                    ("Стажировка React без оплаты", None), ("React", {"from": 0, "currency": "RUB"})):
            with self.subTest(description=description):
                self.assertFalse(rank_lead({"source": "hh", "title": "React Intern",
                                           "description": description, "salary": salary})["eligible"])

    def test_paid_worldwide_and_salary_rules_for_regular_jobs(self):
        self.assertFalse(rank_lead({"source": "remotive", "title": "Paid Frontend Internship",
                                   "location": "Worldwide", "description": "React"})["eligible"])
        self.assertFalse(rank_lead({"source": "hh", "title": "Junior React",
                                    "salary": {"from": 30000, "currency": "RUB"}})["eligible"])

    def test_other_requirements_still_apply(self):
        base = {"source": "hh", "title": "Paid Frontend Intern", "description": "React", "location": "Россия", "salary": {"from": 15000, "currency": "RUB"}}
        for overrides in ({"title": "Paid Senior Frontend Intern"}, {"title": "Paid Junior+ React Intern"},
                          {"requirements": "SQL required"}, {"requirements": "Angular required"},
                          {"description": "Must reside in the US. React"}, {"title": "Paid HR Intern"}):
            with self.subTest(overrides=overrides):
                self.assertFalse(rank_lead({**base, **overrides})["eligible"])

    def test_title_boundaries(self):
        self.assertFalse(is_entry_level("International React Developer"))
        self.assertFalse(is_entry_level("React Developer — practical projects"))
        self.assertTrue(placement_is_paid({"title": "Практикант React", "description": "Оплата: 15000 руб"}))
        self.assertFalse(placement_is_paid({"title": "Frontend Intern", "description": "React. Paid vacation."}))


if __name__ == "__main__":
    unittest.main()
