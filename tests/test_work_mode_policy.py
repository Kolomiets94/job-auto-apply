"""Regression tests for conservative employment work-mode filtering."""
import unittest

from profit_ranker import _work_format_rejection, _work_mode


class WorkModePolicyTests(unittest.TestCase):
    def test_hh_missing_work_mode_is_unknown_not_remote(self):
        lead = {"source": "hh", "title": "Junior Frontend Developer"}
        self.assertEqual(_work_mode(lead), "unknown")
        self.assertEqual(
            _work_format_rejection(lead),
            "remote work format is not confirmed",
        )

    def test_explicit_remote_is_allowed(self):
        lead = {"source": "hh", "work_mode": "remote"}
        self.assertEqual(_work_mode(lead), "remote")
        self.assertIsNone(_work_format_rejection(lead))

    def test_office_is_rejected(self):
        lead = {"source": "hh", "work_mode": "office"}
        self.assertEqual(
            _work_format_rejection(lead),
            "office work is excluded; fully remote only",
        )

    def test_hybrid_only_in_yekaterinburg(self):
        outside = {
            "source": "hh",
            "work_mode": "hybrid",
            "city": "Moscow",
        }
        yekaterinburg = {
            "source": "hh",
            "work_mode": "hybrid",
            "city": "Екатеринбург",
        }
        self.assertEqual(
            _work_format_rejection(outside),
            "hybrid is allowed only in Yekaterinburg",
        )
        self.assertIsNone(_work_format_rejection(yekaterinburg))

    def test_remote_only_source_can_infer_remote(self):
        lead = {"source": "remoteok"}
        self.assertEqual(_work_mode(lead), "remote")
        self.assertIsNone(_work_format_rejection(lead))

    def test_freelance_does_not_use_employment_work_mode_gate(self):
        lead = {"source": "freelancer_com"}
        self.assertIsNone(_work_format_rejection(lead))


if __name__ == "__main__":
    unittest.main()
