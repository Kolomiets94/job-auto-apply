import unittest

from profit_ranker import _manual_review_metadata


class ManualReviewMetadataTests(unittest.TestCase):
    def test_target_stack_only_in_description_is_flagged(self):
        result = _manual_review_metadata(
            {"title": "Web Developer", "description": "Build interfaces with React, HTML and CSS"},
            "job title outside target roles",
        )
        self.assertTrue(result["manual_review_required"])
        self.assertFalse(result["eligible"])

    def test_frontend_without_junior_signal_is_flagged_not_eligible(self):
        result = _manual_review_metadata(
            {"title": "Frontend Developer", "description": "React, TypeScript"},
            "not Junior or 0-3 years",
        )
        self.assertTrue(result["manual_review_required"])
        self.assertFalse(result["eligible"])

    def test_layout_without_entry_signal_is_flagged_not_eligible(self):
        result = _manual_review_metadata(
            {"title": "HTML/CSS верстальщик"},
            "layout entry level not confirmed",
        )
        self.assertTrue(result["manual_review_required"])
        self.assertFalse(result["eligible"])

    def test_unrelated_rejection_is_not_flagged(self):
        result = _manual_review_metadata(
            {"title": "Senior Product Manager", "description": "Roadmaps"},
            "job title outside target roles",
        )
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
