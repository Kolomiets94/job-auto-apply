import unittest

from worker import build_manual_review_list


class ManualReviewListTests(unittest.TestCase):
    def test_includes_linked_borderline_vacancy_without_changing_eligibility(self):
        leads = [{
            "title": "Frontend Developer",
            "source": "hh",
            "url": "https://hh.ru/vacancy/123",
            "description": "React and TypeScript",
            "ats_score": 82,
        }]
        items = build_manual_review_list(leads)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://hh.ru/vacancy/123")
        self.assertEqual(items[0]["ats_score"], 82)

    def test_omits_non_flagged_and_unlinked_leads(self):
        leads = [
            {"title": "Senior Product Manager", "description": "Roadmaps", "url": "https://example.com/1"},
            {"title": "Frontend Developer", "description": "React", "url": ""},
        ]
        self.assertEqual(build_manual_review_list(leads), [])

    def test_respects_limit(self):
        leads = [
            {"title": "Frontend Developer", "source": "hh", "url": f"https://hh.ru/vacancy/{i}",
             "description": "React"}
            for i in range(12)
        ]
        self.assertEqual(len(build_manual_review_list(leads, limit=5)), 5)


if __name__ == "__main__":
    unittest.main()
