import unittest
from unittest.mock import patch

from ats_evaluator import build_manual_review_report


class ManualReviewReportTests(unittest.TestCase):
    @patch("profit_ranker.rank_lead")
    def test_lists_borderline_and_strong_ats_rejections(self, rank_lead):
        rank_lead.side_effect = [
            {"eligible": False, "manual_review_required": True,
             "manual_review_reason": "Junior signal missing",
             "rank_reason": "not Junior or 0-3 years"},
            {"eligible": False, "rank_reason": "location restriction"},
            {"eligible": False, "rank_reason": "SQL outside confirmed stack"},
        ]
        leads = [
            {"title": "Frontend Developer", "source": "hh",
             "url": "https://hh.ru/vacancy/1", "ats_score": 84,
             "ats_verdict": "strong_match"},
            {"title": "React Developer", "source": "remoteok",
             "url": "https://example.com/jobs/2", "ats_score": 91,
             "ats_verdict": "strong_match"},
            {"title": "Frontend Intern", "source": "hh",
             "url": "https://hh.ru/vacancy/3", "ats_score": 52,
             "ats_verdict": "weak_match"},
        ]

        report = build_manual_review_report(leads)

        self.assertIn("Frontend Developer", report)
        self.assertIn("https://hh.ru/vacancy/1", report)
        self.assertIn("Junior signal missing", report)
        self.assertIn("React Developer", report)
        self.assertIn("https://example.com/jobs/2", report)
        self.assertNotIn("Frontend Intern", report)
        self.assertIn("Все вакансии в списке остаются исключёнными", report)

    @patch("profit_ranker.rank_lead")
    def test_does_not_list_eligible_vacancies(self, rank_lead):
        rank_lead.return_value = {"eligible": True}
        report = build_manual_review_report([
            {"title": "Junior Frontend", "source": "hh",
             "url": "https://hh.ru/vacancy/4", "ats_score": 95,
             "ats_verdict": "strong_match"}
        ])
        self.assertIn("таких вакансий нет", report)
        self.assertNotIn("https://hh.ru/vacancy/4", report)

    def test_empty_input_is_safe(self):
        report = build_manual_review_report([])
        self.assertIn("таких вакансий нет", report)


if __name__ == "__main__":
    unittest.main()
