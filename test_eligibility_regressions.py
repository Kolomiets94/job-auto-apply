import unittest

from ats_evaluator import review_lead
from entry_level import is_entry_level
from profit_ranker import _work_mode, _work_format_rejection, rank_lead


class EligibilityRegressionTests(unittest.TestCase):
    def test_hh_without_format_stays_unknown(self):
        self.assertEqual(_work_mode({"source": "hh", "title": "Junior React Developer"}), "unknown")

    def test_all_domestic_formats_are_allowed(self):
        for mode in ("remote", "hybrid", "office", "unknown"):
            with self.subTest(mode=mode):
                self.assertIsNone(_work_format_rejection({"source": "hh", "work_mode": mode}))

    def test_entry_level_synonyms_are_recognized(self):
        for title in ("Graduate Frontend Engineer", "Entry-level React Developer", "Начинающий специалист Frontend", "Junior+ React Developer"):
            with self.subTest(title=title):
                self.assertTrue(is_entry_level(title))

    def test_optional_sql_does_not_reject(self):
        lead = {
            "source": "hh", "title": "Junior React Developer", "location": "Россия",
            "experience": "Нет опыта", "salary": {"from": 60000, "to": 60000, "currency": "RUB"},
            "description": "React и TypeScript. SQL будет плюсом.",
        }
        self.assertTrue(rank_lead(lead)["eligible"])

    def test_explicitly_required_sql_is_rejected(self):
        lead = {
            "source": "hh", "title": "Junior React Developer", "location": "Россия",
            "experience": "Нет опыта", "salary": {"from": 60000, "to": 60000, "currency": "RUB"},
            "description": "React. SQL is required.",
        }
        result = rank_lead(lead)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["rank_reason"], "SQL outside confirmed stack")

    def test_mandatory_business_travel_is_rejected(self):
        lead = {
            "source": "hh", "title": "Junior React Developer", "location": "Россия",
            "experience": "Нет опыта", "salary": {"from": 60000, "to": 60000, "currency": "RUB"},
            "description": "Готовность к командировкам обязательна.",
        }
        result = rank_lead(lead)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["rank_reason"], "mandatory business travel")

    def test_ats_reads_requirements_even_when_description_exists(self):
        result = review_lead({
            "title": "Junior React Developer",
            "description": "React and TypeScript",
            "requirements": "Node.js is required",
            "experience": "No experience",
        }, "React TypeScript projects")
        self.assertIn("node.js", result["ats_missing_keywords"])
        self.assertIn("node.js", result["ats_required_missing_keywords"])


if __name__ == "__main__":
    unittest.main()
